from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Question
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'prepedge-secret-key-change-in-prod'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///prepedge.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin authorization required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

with app.app_context():
    db.create_all()

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username').strip()
        email = request.form.get('email').strip()
        password = request.form.get('password')
        role = request.form.get('role', 'student')

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))

        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    total_questions = Question.query.count() if current_user.role == 'admin' else 0
    return render_template('dashboard.html', total_questions=total_questions)

@app.route('/admin/questions')
@login_required
@admin_required
def admin_questions():
    questions = Question.query.all()
    return render_template('admin_questions.html', questions=questions)

@app.route('/admin/questions/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_question():
    if request.method == 'POST':
        q = Question(
            category=request.form.get('category'),
            company=request.form.get('company', 'General').strip(),
            question_text=request.form.get('question_text').strip(),
            option_a=request.form.get('option_a').strip(),
            option_b=request.form.get('option_b').strip(),
            option_c=request.form.get('option_c').strip(),
            option_d=request.form.get('option_d').strip(),
            correct_option=request.form.get('correct_option'),
            explanation=request.form.get('explanation').strip()
        )
        db.session.add(q)
        db.session.commit()
        flash('Question added successfully!', 'success')
        return redirect(url_for('admin_questions'))
    return render_template('add_question.html')

@app.route('/admin/questions/delete/<int:q_id>', methods=['POST'])
@login_required
@admin_required
def delete_question(q_id):
    q = Question.query.get_or_404(q_id)
    db.session.delete(q)
    db.session.commit()
    flash('Question deleted successfully.', 'info')
    return redirect(url_for('admin_questions'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)