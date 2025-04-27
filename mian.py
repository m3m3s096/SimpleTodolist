from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from datetime import datetime
import json
import os
from functools import wraps
from flask_cors import CORS
import hashlib

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
app.secret_key = 'your-secret-key-here'  # Change this to a secure secret key

USERS_FILE = 'users.json'
DATA_FILE = 'todos.json'
PRIORITIES = {'low': 0, 'medium': 1, 'high': 2}  # Priority levels

def init_data():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w') as f:
            json.dump([], f)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w') as f:
            json.dump({}, f)

def load_users():
    with open(USERS_FILE, 'r') as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def load_todos():
    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
        # Ensure data is a dictionary
        if not isinstance(data, dict):
            data = {}
        # Convert string keys to integers
        return {int(k): v for k, v in data.items()}

def save_todos(todos):
    with open(DATA_FILE, 'w') as f:
        # Convert integer keys to strings for JSON serialization
        json.dump({str(k): v for k, v in todos.items()}, f, indent=2)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return api_response(False, "Authentication required", None, 401)
        return f(*args, **kwargs)
    return decorated_function

def api_response(success: bool, message: str = None, data = None, status_code: int = 200):
    """
    Create a standardized API response
    """
    response = {
        'success': success,
        'message': message,
        'data': data
    }
    return jsonify(response), status_code

def handle_errors(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            return api_response(False, str(e), None, 500)
    return wrapped

# Auth Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        users = load_users()
        user = next((user for user in users if user['username'] == username and user['password'] == hash_password(password)), None)
        
        if user:
            session['user_id'] = user['id']
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Неверное имя пользователя или пароль')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            return render_template('register.html', error='Пароли не совпадают')
        
        users = load_users()
        if any(user['username'] == username for user in users):
            return render_template('register.html', error='Пользователь с таким именем уже существует')
        
        new_user = {
            'id': len(users) + 1,
            'username': username,
            'password': hash_password(password)
        }
        
        users.append(new_user)
        save_users(users)
        
        # Create empty todos list for new user
        todos = load_todos()
        todos[str(new_user['id'])] = []
        save_todos(todos)
        
        session['user_id'] = new_user['id']
        return redirect(url_for('index'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

# Web Routes
@app.route('/')
@login_required
def index():
    todos = load_todos()
    user_todos = todos.get(session['user_id'], [])
    
    for todo in user_todos:
        if 'due_date' in todo and todo['due_date'] and not todo['done']:
            due_date = datetime.strptime(todo['due_date'], '%Y-%m-%d')
            todo['overdue'] = due_date.date() < datetime.now().date()
    
    user_todos.sort(key=lambda x: (
        1 if x['done'] else 0,
        -PRIORITIES.get(x.get('priority', 'low'), 0),
        x['due_date'] if 'due_date' in x and x['due_date'] else '9999-99-99'
    ))
    
    return render_template('index.html', todos=user_todos, priorities=PRIORITIES)

# API Routes
@app.route('/api/todos', methods=['GET'])
@api_login_required
@handle_errors
def api_get_todos():
    """Get all todos for current user"""
    todos = load_todos()
    user_todos = todos.get(session['user_id'], [])
    
    for todo in user_todos:
        if 'due_date' in todo and todo['due_date'] and not todo['done']:
            due_date = datetime.strptime(todo['due_date'], '%Y-%m-%d')
            todo['overdue'] = due_date.date() < datetime.now().date()
    
    user_todos.sort(key=lambda x: (
        1 if x['done'] else 0,
        -PRIORITIES.get(x.get('priority', 'low'), 0),
        x['due_date'] if 'due_date' in x and x['due_date'] else '9999-99-99'
    ))
    
    return api_response(data=user_todos)

@app.route('/api/todos', methods=['POST'])
@api_login_required
@handle_errors
def api_add_todo():
    """Add a new todo for current user"""
    task = request.form.get('task') or request.json.get('task')
    due_date = request.form.get('due_date') or request.json.get('due_date', None)
    priority = request.form.get('priority') or request.json.get('priority', 'low')
    
    if not task:
        return api_response(False, "Task is required", None, 400)
    
    todos = load_todos()
    user_todos = todos.get(session['user_id'], [])
    
    new_task = {
        'id': len(user_todos) + 1,
        'task': task,
        'done': False,
        'priority': priority,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    if due_date:
        new_task['due_date'] = due_date
    
    user_todos.append(new_task)
    todos[session['user_id']] = user_todos
    save_todos(todos)
    
    return api_response(True, "Todo created", new_task, 201)

@app.route('/api/todos/<int:todo_id>/priority', methods=['PUT'])
@api_login_required
@handle_errors
def api_update_priority(todo_id):
    """Update todo priority
    ---
    parameters:
      - name: todo_id
        in: path
        type: integer
        required: true
      - name: priority
        in: formData
        type: string
        enum: [low, medium, high]
        required: true
    responses:
      200:
        description: Priority updated
      404:
        description: Todo not found
    """
    priority = request.form.get('priority') or request.json.get('priority')
    if not priority or priority not in PRIORITIES:
        return api_response(False, "Invalid priority", None, 400)
    
    todos = load_todos()
    user_todos = todos.get(session['user_id'], [])
    found = False
    
    for todo in user_todos:
        if todo['id'] == todo_id:
            todo['priority'] = priority
            found = True
            break
    
    if not found:
        return api_response(False, "Todo not found", None, 404)
    
    todos[session['user_id']] = user_todos
    save_todos(todos)
    return api_response(True, "Priority updated")

@app.route('/api/todos/<int:todo_id>/complete', methods=['PUT'])
@api_login_required
@handle_errors
def api_complete_todo(todo_id):
    """Mark todo as complete
    ---
    parameters:
      - name: todo_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Todo marked as complete
      404:
        description: Todo not found
    """
    todos = load_todos()
    user_todos = todos.get(session['user_id'], [])
    found = False
    
    for todo in user_todos:
        if todo['id'] == todo_id:
            todo['done'] = True
            found = True
            break
    
    if not found:
        return api_response(False, "Todo not found", None, 404)
    
    todos[session['user_id']] = user_todos
    save_todos(todos)
    return api_response(True, "Todo marked as complete")

@app.route('/api/todos/<int:todo_id>', methods=['DELETE'])
@api_login_required
@handle_errors
def api_delete_todo(todo_id):
    """Delete a todo
    ---
    parameters:
      - name: todo_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Todo deleted
      404:
        description: Todo not found
    """
    todos = load_todos()
    user_todos = todos.get(session['user_id'], [])
    initial_length = len(user_todos)
    
    user_todos = [todo for todo in user_todos if todo['id'] != todo_id]
    
    if len(user_todos) == initial_length:
        return api_response(False, "Todo not found", None, 404)
    
    todos[session['user_id']] = user_todos
    save_todos(todos)
    return api_response(True, "Todo deleted")

@app.route('/api/todos/<int:todo_id>', methods=['PUT'])
@api_login_required
@handle_errors
def api_update_todo(todo_id):
    """Update a todo
    ---
    parameters:
      - name: todo_id
        in: path
        type: integer
        required: true
      - name: task
        in: formData
        type: string
        required: true
      - name: due_date
        in: formData
        type: string
        format: date
      - name: priority
        in: formData
        type: string
        enum: [low, medium, high]
    responses:
      200:
        description: Todo updated
      400:
        description: Task is required
      404:
        description: Todo not found
    """
    task = request.form.get('task') or request.json.get('task')
    due_date = request.form.get('due_date') or request.json.get('due_date')
    priority = request.form.get('priority') or request.json.get('priority', 'low')
    
    if not task:
        return api_response(False, "Task is required", None, 400)
    
    todos = load_todos()
    user_todos = todos.get(session['user_id'], [])
    found = False
    
    for todo in user_todos:
        if todo['id'] == todo_id:
            todo['task'] = task
            todo['due_date'] = due_date
            todo['priority'] = priority
            found = True
            break
    
    if not found:
        return api_response(False, "Todo not found", None, 404)
    
    todos[session['user_id']] = user_todos
    save_todos(todos)
    return api_response(True, "Todo updated")

# Web Routes (keep your existing web routes)
@app.route('/add', methods=['POST'])
@login_required
def add():
    task = request.form['task']
    due_date = request.form.get('due_date', None)
    priority = request.form.get('priority', 'low')
    
    if task:
        todos = load_todos()
        user_todos = todos.get(session['user_id'], [])
        
        new_task = {
            'id': len(user_todos) + 1,
            'task': task,
            'done': False,
            'priority': priority,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        if due_date:
            new_task['due_date'] = due_date
        
        user_todos.append(new_task)
        todos[session['user_id']] = user_todos
        save_todos(todos)
    
    return redirect(url_for('index'))

@app.route('/update_priority/<int:todo_id>/<priority>')
@login_required
def update_priority(todo_id, priority):
    todos = load_todos()
    user_todos = todos.get(session['user_id'], [])
    
    for todo in user_todos:
        if todo['id'] == todo_id:
            todo['priority'] = priority
            break
    
    todos[session['user_id']] = user_todos
    save_todos(todos)
    return redirect(url_for('index'))

@app.route('/complete/<int:todo_id>')
@login_required
def complete(todo_id):
    todos = load_todos()
    user_todos = todos.get(session['user_id'], [])
    
    for todo in user_todos:
        if todo['id'] == todo_id:
            todo['done'] = True
            break
    
    todos[session['user_id']] = user_todos
    save_todos(todos)
    return redirect(url_for('index'))

@app.route('/delete/<int:todo_id>')
@login_required
def delete(todo_id):
    todos = load_todos()
    user_todos = todos.get(session['user_id'], [])
    user_todos = [todo for todo in user_todos if todo['id'] != todo_id]
    todos[session['user_id']] = user_todos
    save_todos(todos)
    return redirect(url_for('index'))

@app.route('/update/<int:todo_id>', methods=['POST'])
@login_required
def update(todo_id):
    todos = load_todos()
    user_todos = todos.get(session['user_id'], [])
    task = request.form['task']
    due_date = request.form.get('due_date')
    priority = request.form.get('priority', 'low')
    
    for todo in user_todos:
        if todo['id'] == todo_id:
            todo['task'] = task
            todo['due_date'] = due_date
            todo['priority'] = priority
            break
    
    todos[session['user_id']] = user_todos
    save_todos(todos)
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_data()
    app.run(debug=True, port=2424, host="0.0.0.0")