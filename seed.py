"""
Script de seed do NEXO MVP.
Cria as tabelas, insere planos e segmento padrão, e cria o ADMIN master.

Uso:
    python seed.py

Variáveis de ambiente obrigatórias (defina no .env a partir de .env.example):
    ADMIN_MASTER_NOME   - nome do administrador master
    ADMIN_MASTER_EMAIL  - e-mail do administrador master
    ADMIN_MASTER_SENHA  - senha do administrador master
    PLANO_BRONZE_VALOR_MENSAL / PLANO_PRATA_VALOR_MENSAL / PLANO_OURO_VALOR_MENSAL
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

    # Valores comerciais (valor_mensal) NÃO estão definidos na documentação fonte.
    # Não inventamos preços: lemos de variáveis de ambiente e interrompemos o seed
    # se faltar alguma. Veja .env.example para os nomes e exemplos fictícios.
    valores_env = {
        'BRONZE': os.environ.get('PLANO_BRONZE_VALOR_MENSAL'),
        'PRATA': os.environ.get('PLANO_PRATA_VALOR_MENSAL'),
        'OURO': os.environ.get('PLANO_OURO_VALOR_MENSAL'),
    }
    faltando = [k for k, v in valores_env.items() if not v]
    if faltando:
        raise SystemExit(
            "ERRO: defina os valores mensais dos planos no .env antes de rodar o seed.\n"
            "Variáveis ausentes: "
            + ", ".join(f"PLANO_{k}_VALOR_MENSAL" for k in faltando)
            + "\nConsulte .env.example. Os valores comerciais reais devem ser definidos "
            "pela equipe do projeto — não há preço oficial documentado."
        )

    # nivel_dashboard: no PI2 o dashboard técnico NÃO é filtrado por plano.
    # Usamos um único valor operacional (GERENCIAL) para todos os planos.
    # Não há lógica de bloqueio de dashboard por plano.
    planos = [
        {'nome_plano': 'BRONZE',
         'descricao': 'Análise mensal — entrega básica — atendimento básico',
         'valor_mensal': float(valores_env['BRONZE']),
         'qtd_analises_mes': 1,
         'tipo_analise_permitida': 'MENSAL',
         'nivel_entrega_analise': 'BASICA',
         'nivel_dashboard': 'GERENCIAL',
         'nivel_atendimento': 'BAIXO'},
        {'nome_plano': 'PRATA',
         'descricao': 'Análise mensal — entrega completa — atendimento intermediário',
         'valor_mensal': float(valores_env['PRATA']),
         'qtd_analises_mes': 1,
         'tipo_analise_permitida': 'MENSAL',
         'nivel_entrega_analise': 'COMPLETA',
         'nivel_dashboard': 'GERENCIAL',
         'nivel_atendimento': 'MEDIO'},
        {'nome_plano': 'OURO',
         'descricao': 'Análise quinzenal — entrega premium — atendimento prioritário',
         'valor_mensal': float(valores_env['OURO']),
         'qtd_analises_mes': 2,
         'tipo_analise_permitida': 'QUINZENAL',
         'nivel_entrega_analise': 'PREMIUM',
         'nivel_dashboard': 'GERENCIAL',
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

    # Admin master — sem fallback hardcoded. Todas as variáveis são obrigatórias.
    admin_nome = os.environ.get('ADMIN_MASTER_NOME')
    admin_email = os.environ.get('ADMIN_MASTER_EMAIL')
    admin_senha = os.environ.get('ADMIN_MASTER_SENHA')

    admin_faltando = [
        nome for nome, valor in (
            ('ADMIN_MASTER_NOME', admin_nome),
            ('ADMIN_MASTER_EMAIL', admin_email),
            ('ADMIN_MASTER_SENHA', admin_senha),
        ) if not valor
    ]
    if admin_faltando:
        raise SystemExit(
            "ERRO: variável "
            + ", ".join(admin_faltando)
            + " não definida. Crie um .env a partir de .env.example."
        )

    admin_email = admin_email.strip().lower()
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
