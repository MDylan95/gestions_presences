from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

# ==================== INITIALISATION ====================
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:0000@localhost/gestion_presences'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'dev'

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ==================== MODELES ====================
class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Employe(db.Model):
    __tablename__ = 'employe'
    matricule = db.Column(db.String(20), primary_key=True)
    nom = db.Column(db.String(50), nullable=False)
    prenom = db.Column(db.String(50), nullable=False)
    presences = db.relationship('Presence', backref='employe', lazy=True)

class Presence(db.Model):
    __tablename__ = 'presence'
    id = db.Column(db.Integer, primary_key=True)
    matricule = db.Column(db.String(20), db.ForeignKey('employe.matricule'), nullable=False)
    heure_entree = db.Column(db.DateTime, nullable=False)
    heure_sortie = db.Column(db.DateTime, nullable=True)

    def heures_travaillees(self):
        if self.heure_sortie and self.heure_entree:
            delta = self.heure_sortie - self.heure_entree
            return round(delta.total_seconds() / 3600, 2)
        return None

# ==================== CREATION DES TABLES ====================
with app.app_context():
    db.create_all()
    if not User.query.filter_by(email='admin@example.com').first():
        admin = User(email='admin@example.com', password=generate_password_hash('1234'))
        db.session.add(admin)
        db.session.commit()

# ==================== LOGIN ====================
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password'].strip()
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Email ou mot de passe incorrect', 'error')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ==================== ROUTES PRINCIPALES ====================
@app.route('/')
@login_required
def index():
    total_employes = Employe.query.count()
    today = datetime.now().date()
    presences_today = Presence.query.filter(db.func.date(Presence.heure_entree) == today).count()
    return render_template('index.html', total_employes=total_employes, presences_today=presences_today)

# ----- Liste des employés -----
@app.route('/employes')
@login_required
def list_employes():
    employes = Employe.query.order_by(Employe.matricule).all()
    return render_template('employees.html', employes=employes)

@app.route('/employes/add', methods=['POST'])
@login_required
def add_employe():
    matricule = request.form.get('matricule', '').strip()
    nom = request.form.get('nom', '').strip()
    prenom = request.form.get('prenom', '').strip()
    if not matricule or not nom or not prenom:
        flash('Tous les champs sont requis.', 'error')
        return redirect(url_for('list_employes'))
    if Employe.query.get(matricule):
        flash('Ce matricule existe déjà.', 'error')
        return redirect(url_for('list_employes'))
    emp = Employe(matricule=matricule, nom=nom, prenom=prenom)
    db.session.add(emp)
    db.session.commit()
    flash(f'Employé {nom} {prenom} ajouté.', 'success')
    return redirect(url_for('list_employes'))

# ----- Modifier un employé -----
@app.route('/edit_employe/<string:matricule>', methods=['GET', 'POST'])
@login_required
def edit_employe(matricule):
    employe = Employe.query.get_or_404(matricule)
    if request.method == 'POST':
        employe.matricule = request.form['matricule']
        employe.nom = request.form['nom']
        employe.prenom = request.form['prenom']
        db.session.commit()
        flash(f'Employé {employe.nom} {employe.prenom} modifié.', 'success')
        return redirect(url_for('list_employes'))
    return render_template('edit_employe.html', employe=employe)

# ----- Supprimer un employé -----
@app.route('/delete_employe/<string:matricule>', methods=['POST'])
@login_required
def delete_employe(matricule):
    employe = Employe.query.get_or_404(matricule)
    db.session.delete(employe)
    db.session.commit()
    flash(f'Employé {employe.nom} {employe.prenom} supprimé.', 'success')
    return redirect(url_for('list_employes'))

# ----- Enregistrer présence (Entrée) -----
@app.route('/entry/<string:matricule>', methods=['POST'])
@login_required
def entry(matricule):
    emp = Employe.query.get(matricule)
    if not emp:
        flash('Matricule non trouvé.', 'error')
        return redirect(url_for('presences_enregistrer'))

    # Définir le début et la fin de la journée actuelle
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # Vérifier s'il existe déjà une présence pour ce matricule aujourd'hui
    presence_existante = Presence.query.filter(
        Presence.matricule == matricule,
        Presence.heure_entree >= today_start,
        Presence.heure_entree < today_end
    ).first()

    # Si une présence a déjà été enregistrée pour aujourd'hui, on empêche une nouvelle entrée.
    if presence_existante:
        flash(f"L'employé {emp.nom} {emp.prenom} a déjà enregistré son entrée pour aujourd'hui.", 'error')
        return redirect(url_for('presences_enregistrer'))

    # Si aucune entrée n'est trouvée pour aujourd'hui, on procède à l'enregistrement
    now = datetime.now()
    p = Presence(matricule=matricule, heure_entree=now)
    db.session.add(p)
    db.session.commit()
    
    flash(f"Entrée enregistrée pour {emp.nom} {emp.prenom} à {now.strftime('%d-%m-%Y %H:%M:%S')}", 'success')
    return redirect(url_for('presences_enregistrer'))


# ----- Enregistrer sortie -----
@app.route('/exit/<string:matricule>', methods=['POST'])
@login_required
def exit_(matricule):
    emp = Employe.query.get(matricule)
    if not emp:
        flash('Matricule non trouvé.', 'error')
        return redirect(url_for('presences_enregistrer'))
    
    # Chercher la dernière entrée non clôturée
    p = Presence.query.filter_by(matricule=matricule, heure_sortie=None).order_by(Presence.heure_entree.desc()).first()
    
    if not p:
        flash('Aucune entrée ouverte pour cet employé.', 'error')
        return redirect(url_for('presences_enregistrer'))
    
    p.heure_sortie = datetime.now()
    db.session.commit()
    flash(f'Sortie enregistrée pour {emp.nom} {emp.prenom} à {p.heure_sortie.strftime("%d-%m-%Y %H:%M:%S")}', 'success')
    return redirect(url_for('presences_enregistrer'))

# ----- Page pour enregistrer présence -----
@app.route('/presences/enregistrer')
@login_required
def presences_enregistrer():
    employes = Employe.query.options(db.joinedload(Employe.presences)).order_by(Employe.matricule).all()
    return render_template('list_employes.html', employes=employes, now=datetime.now())


# ----- Liste des présences du jour -----
@app.route('/presences/jour')
@login_required
def presences_jour():
    today = datetime.now().date()
    presences = Presence.query.filter(db.func.date(Presence.heure_entree) == today).order_by(Presence.heure_entree.desc()).all()
    return render_template('list_presences.html', presences=presences, today_date=today.strftime('%d %B %Y'))

# ----- Historique 1 an -----
@app.route('/presences/historique')
@login_required
def historique_presences():
    today = datetime.now()
    last_year = today - timedelta(days=365)
    presences = Presence.query.filter(Presence.heure_entree >= last_year).order_by(Presence.heure_entree.desc()).all()
    
    # Calculer le total des heures travaillées
    total_hours = sum(p.heures_travaillees() or 0 for p in presences if p.heures_travaillees() is not None)
    
    return render_template(
        'historique.html', 
        presences=presences,
        total_hours=total_hours
    )

# ... (code précédent) ...

# ----- Page de paramètres -----
@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    user = current_user

    if request.method == 'POST':
        # Logique pour la mise à jour de l'email
        if 'update_email' in request.form:
            new_email = request.form.get('email', '').strip()
            if not new_email:
                flash('L\'email ne peut pas être vide.', 'error')
            elif new_email != user.email and User.query.filter_by(email=new_email).first():
                flash('Cet e-mail est déjà utilisé.', 'error')
            else:
                user.email = new_email
                db.session.commit()
                flash('Votre e-mail a été mis à jour avec succès.', 'success')
            return redirect(url_for('settings'))

        # Logique pour la mise à jour du mot de passe
        if 'update_password' in request.form:
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')

            if not check_password_hash(user.password, current_password):
                flash('Le mot de passe actuel est incorrect.', 'error')
            elif new_password != confirm_password:
                flash('Les nouveaux mots de passe ne correspondent pas.', 'error')
            else:
                user.password = generate_password_hash(new_password)
                db.session.commit()
                flash('Votre mot de passe a été mis à jour avec succès.', 'success')
            return redirect(url_for('settings'))

    return render_template('settings.html')

# ==================== LANCEMENT ====================
if __name__ == '__main__':
    app.run(debug=True)