import os
from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Question, TestResult
from functools import wraps
from sqlalchemy import func

app = Flask(__name__)
app.config['SECRET_KEY'] = 'prepedge-secret-key-change-in-prod'

# Use writable /tmp directory on Vercel serverless environment, local SQLite path otherwise
if os.environ.get('VERCEL'):
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/prepedge.db'
else:
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
    
    user_results = TestResult.query.filter_by(user_id=current_user.id).order_by(TestResult.date_taken.desc()).all()
    
    total_tests = len(user_results)
    avg_score = round(sum(r.percentage for r in user_results) / total_tests, 1) if total_tests > 0 else 0
    
    category_stats = {}
    for r in user_results:
        if r.category not in category_stats:
            category_stats[r.category] = {'count': 0, 'total_pct': 0}
        category_stats[r.category]['count'] += 1
        category_stats[r.category]['total_pct'] += r.percentage
        
    for cat in category_stats:
        category_stats[cat]['avg'] = round(category_stats[cat]['total_pct'] / category_stats[cat]['count'], 1)

    return render_template(
        'dashboard.html', 
        total_questions=total_questions, 
        recent_tests=user_results[:5],
        total_tests=total_tests,
        avg_score=avg_score,
        category_stats=category_stats
    )

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

@app.route('/tests')
@login_required
def test_selection():
    categories = db.session.query(Question.category).distinct().all()
    category_list = [c[0] for c in categories]
    return render_template('test_selection.html', categories=category_list)

@app.route('/test/start/<category>')
@login_required
def start_test(category):
    questions = Question.query.filter_by(category=category).all()
    if not questions:
        flash(f'No questions available for {category}.', 'warning')
        return redirect(url_for('test_selection'))
    time_limit_minutes = 2
    return render_template(
        'take_test.html', 
        category=category, 
        questions=questions, 
        time_limit=time_limit_minutes,
        submit_url=url_for('submit_test', category=category)
    )

@app.route('/test/submit/<category>', methods=['POST'])
@login_required
def submit_test(category):
    questions = Question.query.filter_by(category=category).all()
    score = 0
    total = len(questions)
    review_data = []

    for q in questions:
        selected_option = request.form.get(f'question_{q.id}')
        is_correct = (selected_option == q.correct_option)
        if is_correct:
            score += 1
        
        review_data.append({
            'question': q,
            'selected': selected_option,
            'is_correct': is_correct
        })

    percentage = round((score / total) * 100, 2) if total > 0 else 0

    result = TestResult(
        user_id=current_user.id,
        category=category,
        total_questions=total,
        score=score,
        percentage=percentage
    )
    db.session.add(result)
    db.session.commit()

    return render_template('test_result.html', category=category, score=score, total=total, percentage=percentage, review_data=review_data)

@app.route('/company-sets')
@login_required
def company_selection():
    companies = db.session.query(Question.company).distinct().all()
    company_list = [c[0] for c in companies if c[0] and c[0] != 'General']
    return render_template('company_selection.html', companies=company_list)

@app.route('/company-test/start/<company>')
@login_required
def start_company_test(company):
    questions = Question.query.filter_by(company=company).all()
    if not questions:
        flash(f'No company-specific questions available for {company}.', 'warning')
        return redirect(url_for('company_selection'))
    time_limit_minutes = 3
    return render_template(
        'take_test.html', 
        category=f"{company} Special", 
        questions=questions, 
        time_limit=time_limit_minutes,
        submit_url=url_for('submit_company_test', company=company)
    )

@app.route('/company-test/submit/<company>', methods=['POST'])
@login_required
def submit_company_test(company):
    questions = Question.query.filter_by(company=company).all()
    score = 0
    total = len(questions)
    review_data = []

    for q in questions:
        selected_option = request.form.get(f'question_{q.id}')
        is_correct = (selected_option == q.correct_option)
        if is_correct:
            score += 1
        
        review_data.append({
            'question': q,
            'selected': selected_option,
            'is_correct': is_correct
        })

    percentage = round((score / total) * 100, 2) if total > 0 else 0

    result = TestResult(
        user_id=current_user.id,
        category=f"{company} Special",
        total_questions=total,
        score=score,
        percentage=percentage
    )
    db.session.add(result)
    db.session.commit()

    return render_template('test_result.html', category=f"{company} Special", score=score, total=total, percentage=percentage, review_data=review_data)

@app.route('/leaderboard')
@login_required
def leaderboard():
    leaderboard_query = db.session.query(
        User.username,
        func.count(TestResult.id).label('tests_taken'),
        func.sum(TestResult.score).label('total_score'),
        func.avg(TestResult.percentage).label('avg_percentage')
    ).join(TestResult, User.id == TestResult.user_id)\
     .group_by(User.id)\
     .order_by(func.avg(TestResult.percentage).desc(), func.count(TestResult.id).desc())\
     .all()

    formatted_leaderboard = []
    for rank, row in enumerate(leaderboard_query, start=1):
        formatted_leaderboard.append({
            'rank': rank,
            'username': row.username,
            'tests_taken': row.tests_taken,
            'total_score': row.total_score,
            'avg_percentage': round(row.avg_percentage, 1)
        })

    return render_template('leaderboard.html', leaderboard=formatted_leaderboard)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)