from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
from io import BytesIO
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = 's3cr3tk3y'

# Função para inicializar o banco de dados SQLite
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Criar tabela products com a coluna active
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL,
            active BOOLEAN DEFAULT TRUE
        )
    ''')
    
    # Criar tabela users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')
    
    # Criar tabela sales
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            total REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Inicializar o banco de dados
init_db()

# Rota para página inicial
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE active = TRUE')
    products = cursor.fetchall()
    conn.close()
    return render_template('index.html', products=products)

# Rota para registro de usuário
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
            conn.commit()
        except sqlite3.IntegrityError:
            flash('Username already exists')
            return redirect(url_for('register'))
        conn.close()
        flash('User registered successfully')
        return redirect(url_for('login'))
    return render_template('register.html')

# Rota para login de usuário
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect(url_for('index'))
        flash('Invalid username or password')
    return render_template('login.html')

# Rota para logout de usuário
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect(url_for('login'))

# Rota para adicionar produto
@app.route('/add_product', methods=['POST'])
def add_product():
    name = request.form['name']
    price = request.form['price']
    stock = request.form['stock']
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO products (name, price, stock) VALUES (?, ?, ?)', (name, price, stock))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

# Rota para registrar venda de produto
@app.route('/sell_product', methods=['POST'])
def sell_product():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Verificar se há estoque suficiente
    cursor.execute('SELECT stock, price FROM products WHERE id=? AND active=TRUE', (product_id,))
    product = cursor.fetchone()
    if product and product[0] >= quantity:
        total = product[1] * quantity

        # Registrar a venda associada ao usuário logado
        cursor.execute('INSERT INTO sales (user_id, product_id, quantity, total) VALUES (?, ?, ?, ?)', (user_id, product_id, quantity, total))
        
        # Atualizar o estoque do produto
        cursor.execute('UPDATE products SET stock = stock - ? WHERE id = ?', (quantity, product_id))

        conn.commit()
        conn.close()

        flash('Venda registrada com sucesso!', 'success')
    else:
        flash(f'Estoque insuficiente para o produto selecionado.', 'error')

    return redirect(url_for('index'))

# Rota para excluir produto
@app.route('/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE products SET active = FALSE WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

# Rota para gerar relatório de vendas
@app.route('/generate_report')
def generate_report():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    if start_date and end_date:
        cursor.execute('''
            SELECT sales.id, users.username, products.name, sales.quantity, sales.total, sales.timestamp
            FROM sales
            JOIN users ON sales.user_id = users.id
            JOIN products ON sales.product_id = products.id
            WHERE DATE(sales.timestamp) BETWEEN ? AND ?
        ''', (start_date, end_date))
    else:
        cursor.execute('''
            SELECT sales.id, users.username, products.name, sales.quantity, sales.total, sales.timestamp
            FROM sales
            JOIN users ON sales.user_id = users.id
            JOIN products ON sales.product_id = products.id
        ''')

    sales = cursor.fetchall()
    conn.close()
    return render_template('report.html', sales=sales)

# Rota para gerar relatório de vendas em PDF
@app.route('/generate_report_pdf')
def generate_report_pdf():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT sales.id, users.username, products.name, sales.quantity, sales.total, sales.timestamp
        FROM sales
        JOIN users ON sales.user_id = users.id
        JOIN products ON sales.product_id = products.id
    ''')
    sales = cursor.fetchall()
    conn.close()

    # Gerar o PDF
    buffer = BytesIO()
    p = canvas.Canvas(buffer)

    p.drawString(100, 800, "Relatório de Vendas")
    y = 750
    for sale in sales:
        p.drawString(100, y, f"ID: {sale[0]}, Usuário: {sale[1]}, Produto: {sale[2]}, Quantidade: {sale[3]}, Total: {sale[4]}, Data: {sale[5]}")
        y -= 20
        if y < 50:
            p.showPage()
            y = 800

    p.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name='relatorio_vendas.pdf', mimetype='application/pdf')

# Inicializar a aplicação Flask
if __name__ == '__main__':
    app.run(debug=True)
