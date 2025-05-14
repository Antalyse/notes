from flask import Flask, render_template, redirect, url_for, request, flash, Response, send_from_directory, send_file, jsonify, abort, current_app
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from sqlalchemy import ForeignKey
from urllib.parse import quote_plus
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "your_very_secret_key_12345")

db_type = os.environ.get('DB_TYPE', "LOCAL")
maximum_note_length = int(os.environ.get('MAXIMUM_NOTE_LENGTH', '4000'))

if db_type == "LOCAL":
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URI", "sqlite:///notes.db")  
elif db_type == "POSTGRES":
    db_service = os.environ.get('DB_SERVICE')
    db_name = os.environ.get('DB_NAME')
    db_user = os.environ.get('DB_USER')
    db_port = os.environ.get('DB_PORT')
    pg_pw = quote_plus(os.environ.get('DB_PASSWORD'))
    database_uri = f"postgresql://{db_user}:{pg_pw}@{db_service}:{db_port}/{db_name}?sslmode=require"
    app.config['SQLALCHEMY_DATABASE_URI'] = database_uri
else:
    raise ValueError(f"Unsupported DB_TYPE: {db_type}. Please use 'LOCAL' or 'POSTGRES'.")


db = SQLAlchemy(app)
migrate = Migrate(app, db)
    
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False) 

    def __repr__(self):
        return f'<User {self.username}>'

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
class Note(db.Model):   
    __tablename__ = 'notes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, ForeignKey('users.id'), nullable=False)
    note = db.Column(db.Text, nullable=False)

with app.app_context():
    db.create_all()


def is_username_available(username):    
    user = User.query.filter_by(username=username).first()
    return {"available": False if user else True}

def password_meets_policy(password):
    status = False
    if len(password) >= 8:
        status = True
    return {"available": status}



@app.route('/favicon.ico') 
def favicon():
    return {"message": "No favicon available"}, 404


@app.route('/')
def home():
      return redirect(url_for('dashboard'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard')) 

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not username:
            flash('Username is required.', 'warning')
            return render_template('register.html', checks={})
        if not password:
            flash('Password is required.', 'warning')
            return render_template('register.html', checks={})
        if password != confirm_password:
            flash('Passwords do not match.', 'warning')
            return render_template('register.html', checks={})

        username_check = is_username_available(username)
        password_policy_check = password_meets_policy(password)

        checks = {
            "username_available": username_check['available'],
            "password_meets_policy": password_policy_check['available']
        }

        if not username_check['available']:
            flash('Username is already taken. Please choose another.', 'danger')
        if not password_policy_check['available']:
            flash(password_policy_check.get('message', 'Password does not meet security requirements.'), 'danger')

        if checks['username_available'] and checks['password_meets_policy']:
            try:
                new_user = User(username=username)
                new_user.set_password(password)
                db.session.add(new_user)
                db.session.commit()
                login_user(new_user)
                return redirect(url_for('dashboard'))
            except Exception as e:
                db.session.rollback() 
                current_app.logger.error(f"Registration error: {e}")
                flash('An unexpected error occurred during registration. Please try again.', 'danger')
                return render_template('register.html', checks=checks)
        else:
            return render_template('register.html', checks=checks, username=username)

    return render_template('register.html', checks={})


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard')) 

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password: 
            flash('Username and password are required.', 'warning')
            return render_template('login.html', error="Username and password are required.")

        try:
            user = User.query.filter_by(username=username).first()

            if user and user.check_password(password):
                login_user(user) 
                flash('Logged in successfully!', 'success')
                next_url = request.args.get('next')
                if next_url and not next_url.startswith(('/', request.host_url)):
                    next_url = None
                return redirect(next_url or url_for('dashboard'))
            else:
                flash('Invalid username or password.', 'danger')
                return render_template('login.html', error="Invalid credentials!", username=username)
        except Exception as e:
            current_app.logger.error(f"Login error: {e}") 
            flash('An unexpected error occurred. Please try again.', 'danger')
            return render_template('login.html', error="Error during login!")

    return render_template('login.html')

@app.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    try:
        notes = Note.query.filter_by(user_id=current_user.id).order_by(Note.id.desc()).all()
    except Exception as e:
        current_app.logger.error(f"Error fetching notes for user {current_user.id}: {e}")
        notes = []
        flash("Could not load your notes at this time.", "error")
    return render_template('dashboard.html', notes=notes, maximum_note_length=maximum_note_length)


@app.route('/add-note', methods=['POST']) 
@login_required
def add_note():
    if request.method == 'POST':
        note_content = request.form.get('note') 
        
        if not note_content or len(note_content.strip()) == 0:
            flash('Note content cannot be empty.', 'warning')
            return redirect(url_for('dashboard')) 

        if len(note_content) > maximum_note_length: 
             flash(f'Note cannot exceed {maximum_note_length} characters. Yours has {len(note_content)}.', 'warning')
             return redirect(url_for('dashboard'))


        try:
            new_note = Note(
                user_id=current_user.id,
                note=note_content.strip() 
            )
            db.session.add(new_note)
            db.session.commit()
            flash('Note added successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error adding note for user {current_user.id}: {e}")
            flash('Error adding note. Please try again.', 'danger')

        return redirect(url_for('dashboard')) 

@app.route('/route/edit/<int:note_id>', methods=['PUT', 'POST']) 
@login_required
def edit_note(note_id):
    note_to_edit = Note.query.filter_by(id=note_id, user_id=current_user.id).first()

    if not note_to_edit:
        return jsonify({"message": "Note not found or you don't have permission to edit it."}), 404

    if request.method == 'PUT' or request.method == 'POST':
        new_content = request.form.get('note')

        if new_content is None: 
            return jsonify({"message": "Missing note content in request."}), 400
        
        trimmed_content = new_content.strip()

        if not trimmed_content:
            return jsonify({"message": "Note content cannot be empty."}), 400 
        
        if len(trimmed_content) > maximum_note_length: 
            return jsonify({"message": f"Note cannot exceed {maximum_note_length} characters. Yours has {len(trimmed_content)}."}), 400


        try:
            note_to_edit.note = trimmed_content
            db.session.commit()
            return jsonify({
                "message": "Note updated successfully!",
                "note": {
                    "id": note_to_edit.id,
                    "note": note_to_edit.note,
                }
            }), 200
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating note {note_id} for user {current_user.id}: {e}")
            return jsonify({"message": "Error updating note. Please try again."}), 500
    
        return jsonify({"message": "Invalid request method. Use PUT or POST."}), 405


@app.route('/route/delete/<int:note_id>', methods=['DELETE'])
@login_required
def delete_route(note_id): 
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first()
    if not note:
        return jsonify({"message": "Note not found or not authorized"}), 404 
    try:
        db.session.delete(note)
        db.session.commit()
        return jsonify({"message": "Note deleted successfully"}), 200 
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting note {note_id} for user {current_user.id}: {e}")
        return jsonify({"message": "Error deleting note"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true')
