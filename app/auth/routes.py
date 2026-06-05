from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import Usuario

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('client.dashboard'))
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('auth.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')

        usuario = Usuario.query.filter_by(email=email).first()

        if not usuario or not usuario.check_password(senha):
            flash('E-mail ou senha inválidos.', 'danger')
            return render_template('auth/login.html')

        if not usuario.ativo:
            flash('Sua conta está desativada. Entre em contato com o suporte.', 'danger')
            return render_template('auth/login.html')

        if usuario.is_cliente:
            empresa = usuario.empresa
            if empresa is None:
                flash('Conta sem empresa associada. Entre em contato com o suporte.', 'danger')
                return render_template('auth/login.html')
            if empresa.status_conta == 'CANCELADA':
                flash('O acesso desta empresa foi cancelado. Entre em contato com o suporte.', 'danger')
                return render_template('auth/login.html')

        login_user(usuario)
        usuario.ultimo_acesso = datetime.utcnow()
        db.session.commit()

        if usuario.is_admin:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('client.dashboard'))

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logout realizado com sucesso.', 'info')
    return redirect(url_for('auth.login'))
