"""
Script de seed do NEXO MVP.
Cria as tabelas, insere planos e segmento padrão, e cria o ADMIN master.

Uso:
    python seed.py

Variáveis de ambiente necessárias (ou defina no .env):
    ADMIN_NOME   - nome do administrador (default: Administrador)
    ADMIN_EMAIL  - e-mail do administrador
    ADMIN_SENHA  - senha do administrador
"""
import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app, db
from app.models import Plano, Segmento, Usuario

app = create_app()

with app.app_context():
    db.create_all()
    print("Tabelas criadas/verificadas.")

    # Planos oficiais
    planos = [
        {'nome_plano': 'BRONZE', 'descricao': 'Análise mensal — atendimento básico',
         'nivel_atendimento': 'BAIXO'},
        {'nome_plano': 'PRATA', 'descricao': 'Análise mensal — atendimento intermediário',
         'nivel_atendimento': 'MEDIO'},
        {'nome_plano': 'OURO', 'descricao': 'Análise quinzenal permitida — atendimento prioritário',
         'nivel_atendimento': 'ALTO'},
    ]
    for p in planos:
        if not Plano.query.filter_by(nome_plano=p['nome_plano']).first():
            plano = Plano(**p, ativo=True)
            db.session.add(plano)
            print(f"  Plano criado: {p['nome_plano']}")

    # Segmento padrão
    seg_nome = 'Tintas e Material de Pintura'
    if not Segmento.query.filter_by(nome_segmento=seg_nome).first():
        seg = Segmento(nome_segmento=seg_nome,
                       descricao='Lojas de tintas, vernizes e materiais de pintura',
                       ativo=True)
        db.session.add(seg)
        print(f"  Segmento criado: {seg_nome}")

    db.session.commit()

    # Admin master
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@nexo.com')
    admin_nome = os.environ.get('ADMIN_NOME', 'Administrador')
    admin_senha = os.environ.get('ADMIN_SENHA')

    if not admin_senha:
        print("\nERRO: defina ADMIN_SENHA no .env antes de rodar o seed.")
    else:
        if not Usuario.query.filter_by(email=admin_email).first():
            admin = Usuario(
                nome=admin_nome,
                email=admin_email,
                role='ADMIN',
                id_empresa=None,
                ativo=True,
            )
            admin.set_password(admin_senha)
            db.session.add(admin)
            db.session.commit()
            print(f"  Admin criado: {admin_email}")
        else:
            print(f"  Admin já existe: {admin_email}")

    print("\nSeed concluído.")
