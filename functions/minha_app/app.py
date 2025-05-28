from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from supabase import create_client, Client
from sqlalchemy import or_ # Importar 'or_' para filtros OR
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta # Adicione ', timedelta' aqui
import pytz
import requests
import feedparser
from math import ceil
from io import BytesIO
from sqlalchemy import func
import psycopg2
import os
from sqlalchemy import or_
import threading 
import random # <--- ADICIONE ESTA LINHA
from bs4 import BeautifulSoup


app = Flask(__name__)
app.config['SECRET_KEY'] = 'sua_chave_secreta_aqui'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres.fjurmbfvfuzhyrwkduav:Qaz241059%23MLP140308@aws-0-us-east-2.pooler.supabase.com:5432/postgres'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Definição dos Modelos do Banco de Dados --- # SISTEMA CRIADO E DESENVOLVIDO POR WELLINGTON CAMPOS: E-MAIL: WCAMPOS241059@GMAIL.COM
# ====================================================================
# DEFINIÇÃO DAS CONSTANTES DE STATUS (ADICIONE OU VERIFIQUE ESTAS)
# ====================================================================
STATUS_REGISTRO_PRINCIPAL = {
    'AGUARDANDO_CARREGAMENTO': 'Aguardando Carregamento',
    'CARREGAMENTO_LIBERADO': 'Carregamento Liberado',
    'EM_CARREGAMENTO': 'Em Carregamento',
    'FINALIZADO': 'Finalizado',
    'CANCELADO': 'Cancelado'
}

# Constantes para os estados de 'em_separacao'
# --- Definições dos Status de 'em_separacao' ---
STATUS_EM_SEPARACAO = {
    'AGUARDANDO_MOTORISTA': 0,
    'SEPARACAO': 1,
    'FINALIZADO': 2, # Manter Finalizado com valor 2
    'CANCELADO': 3,
    'TRANSFERIDO': 4,
    'AGUARDANDO_ENTREGADOR': 5 # Nova chave adicionada
}


# --- Função Auxiliar para Traduzir o Status (para exibir no HTML) ---
def get_status_text(status_code):
    """Traduz o código numérico do status 'em_separacao' para texto amigável."""
    # Criar um mapeamento inverso para facilitar a busca
    status_map = {v: k for k, v in STATUS_EM_SEPARACAO.items()}
    text = status_map.get(status_code, 'DESCONHECIDO')
    return text.replace('_', ' ').title() # Ex: 'AGUARDANDO_MOTORISTA' -> 'Aguardando Motorista'

# --- Seu Modelo NoShow (certifique-se de que está como abaixo) ---
class NoShow(db.Model):
    __tablename__ = 'no_show'
    id = db.Column(db.Integer, primary_key=True)
    data_hora_login = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    nome = db.Column(db.String(100))
    matricula = db.Column(db.String(50))
    gaiola = db.Column(db.String(50)) # Rota
    tipo_entrega = db.Column(db.String(50))
    rua = db.Column(db.String(200))
    estacao = db.Column(db.String(50))
    finalizada = db.Column(db.Integer, default=0) # 0 = não finalizado, 1 = finalizado
    cancelado = db.Column(db.Integer, default=0)  # 0 = não cancelado, 1 = cancelado
    em_separacao = db.Column(db.Integer, default=STATUS_EM_SEPARACAO['AGUARDANDO_MOTORISTA']) # Padrão: 0
    hora_finalizacao = db.Column(db.DateTime)

    def __repr__(self):
        return f"<NoShow {self.id} - {self.nome} - Rota: {self.gaiola}>"



class Registro(db.Model):
    __tablename__ = 'registros'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False)
    matricula = db.Column(db.String(20), nullable=False)
    rota = db.Column(db.String(80))
    tipo_entrega = db.Column(db.String(80))
    cidade_entrega = db.Column(db.String(80))
    rua = db.Column(db.String(80))
    data_hora_login = db.Column(db.DateTime, default=datetime.now)
    tipo_veiculo = db.Column(db.String(80))
    em_separacao = db.Column(db.Integer, default=0)
    gaiola = db.Column(db.String(80))
    estacao = db.Column(db.String(80))
    finalizada = db.Column(db.Integer, default=0)
    hora_finalizacao = db.Column(db.DateTime) # Mude de String para DateTime!
    cancelado = db.Column(db.Integer, default=0)
    login_id = db.Column(db.Integer, db.ForeignKey('login.id'))
    login = db.relationship('Login', backref=db.backref('registros', lazy=True))

    def __repr__(self):
        return f'<Registro {self.matricula} - {self.nome}>'

class Login(db.Model):
    __tablename__ = 'login'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False)
    matricula = db.Column(db.String(20), unique=True, nullable=False)
    tipo_veiculo = db.Column(db.String(80))
    data_cadastro = db.Column(db.DateTime)

class Cidade(db.Model):
    __tablename__ = 'cidades' # Nome da tabela no banco de dados
    id = db.Column(db.Integer, primary_key=True) # Mapeia para SERIAL PRIMARY KEY
    cidade = db.Column(db.String(80), unique=True, nullable=False)
    # ... outras colunas ...


# --- Inicializar Base de Dados (com Flask-SQLAlchemy) ---
def init_db():
    with app.app_context():
        db.create_all()
        print("Banco de dados PostgreSQL inicializado (com Flask-SQLAlchemy).")

# --- Suas funções utilitárias (get_data_hora_brasilia, formata_data_hora) ---
def get_data_hora_brasilia():
    """
    Obtém a data e hora atuais no fuso horário de São Paulo (Brasil)
    como um objeto datetime.
    """
    tz_brasilia = pytz.timezone('America/Sao_Paulo')
    return datetime.now(tz_brasilia) # Retorna o objeto datetime diretamente

def formata_data_hora(data_hora):
    if not data_hora:
        return 'Não Finalizado' # Ou 'Aguarde', o que preferir para nulo

    # Defina o fuso horário de exibição (Brasil/São Paulo)
    tz_destino = pytz.timezone('America/Sao_Paulo')

    if isinstance(data_hora, datetime):
        # Se o objeto datetime NÃO tiver informações de fuso horário,
        # assumimos que ele está em UTC (padrão do PostgreSQL para TIMESTAMP)
        # e o tornamos "aware" (ciente do fuso horário) como UTC.
        if data_hora.tzinfo is None:
            data_hora_utc = pytz.utc.localize(data_hora)
        else:
            # Se já tem tzinfo (ex: já é de Brasília do get_data_hora_brasilia),
            # apenas o converte para UTC primeiro para ser consistente e depois para o tz_destino
            data_hora_utc = data_hora.astimezone(pytz.utc)
        
        # Agora converta o datetime (que está em UTC) para o fuso horário de destino
        data_hora_local = data_hora_utc.astimezone(tz_destino)
        
        return data_hora_local.strftime('%d/%m/%Y %H:%M:%S')
    
    # Se ainda chegar algo que não seja datetime (depois da migração), é um erro.
    return 'Erro de Formato Inesperado'

app.jinja_env.filters['formata_data_hora'] = formata_data_hora
# --- Suas rotas ---
def capitalize_words(text):
    if text:
        return ' '.join(word.capitalize() for word in text.split())
    return None

@app.route('/', methods=['GET', 'POST'])
def login():
    erro = None
    if request.method == 'POST':
        matricula = request.form['matricula']
        nome = request.form['nome'].title()
        rota = request.form.get('rota', '').title()
        tipo_entrega = request.form.get('tipo_entrega', '').title()
        cidade_entrega = request.form.get('cidade_entrega', '').title()
        rua = request.form.get('rua', '').title()

        data_hora_atual = get_data_hora_brasilia()
        data_hoje = data_hora_atual.date()  # Pegando só a data (sem hora)

        with app.app_context():
            user_login = db.session.query(Login).filter_by(matricula=matricula).first()

            if user_login:
                login_id = user_login.id
                tipo_veiculo = user_login.tipo_veiculo

                ## =========================
                ## 🔥 Verificação para No-Show (matricula 0001)
                if matricula == '0001' and tipo_entrega == 'No-Show':
                    if tipo_veiculo.lower() != 'moto':
                        registro_existente = db.session.query(NoShow).filter(
                            NoShow.matricula == matricula,
                            NoShow.tipo_entrega == tipo_entrega,
                            db.func.date(NoShow.data_hora_login) == data_hoje
                        ).first()

                        if registro_existente:
                            erro = f"Já existe um registro com matrícula {matricula} e tipo de entrega {tipo_entrega} para hoje."
                            print(erro)
                            return render_template('login.html', erro=erro)

                    no_show_reg = NoShow(
                        nome=nome,
                        matricula=matricula,
                        rota=rota,
                        tipo_entrega=tipo_entrega,
                        cidade_entrega=cidade_entrega,
                        rua=rua,
                        data_hora_login=data_hora_atual,
                        tipo_veiculo=tipo_veiculo,
                        em_separacao=0,
                        finalizada=0,
                        hora_finalizacao=None,
                        cancelado=0,
                        transferred_to_registro_id=None,
                        login_id=login_id
                    )
                    db.session.add(no_show_reg)
                    db.session.commit()
                    new_session_id = no_show_reg.id
                    print(f"Nova sessão No-Show criada com ID: {new_session_id}")
                    return redirect(url_for('status_motorista', matricula=matricula, registro_id=new_session_id))

                ## =========================
                ## 🔥 Verificação para registros normais (qualquer matrícula)
                if tipo_veiculo.lower() != 'moto':
                    registro_existente = db.session.query(Registro).filter(
                        Registro.matricula == matricula,
                        Registro.tipo_entrega == tipo_entrega,
                        db.func.date(Registro.data_hora_login) == data_hoje
                    ).first()

                    if registro_existente:
                        erro = f"Já existe um registro com matrícula {matricula} e tipo de entrega {tipo_entrega} para hoje."
                        print(erro)
                        return render_template('login.html', erro=erro)

                registro = Registro(
                    nome=nome,
                    matricula=matricula,
                    rota=rota,
                    tipo_entrega=tipo_entrega,
                    cidade_entrega=cidade_entrega,
                    rua=rua,
                    data_hora_login=data_hora_atual,
                    tipo_veiculo=tipo_veiculo,
                    em_separacao=0,
                    finalizada=0,
                    hora_finalizacao=None,
                    cancelado=0,
                    login_id=login_id
                )
                db.session.add(registro)
                db.session.commit()
                new_session_id = registro.id
                print(f"Nova sessão Registro criada com ID: {new_session_id}")
                return redirect(url_for('status_motorista', matricula=matricula, registro_id=new_session_id))

            else:
                erro = 'Número de registro não cadastrado. Por favor, cadastre-se primeiro.'
                print(f"Tentativa de login falhou para matrícula {matricula}: Número de registro não cadastrado.")
                return render_template('login.html', erro=erro)

    return render_template('login.html', erro=erro)

#----Fim da Rota Lgin -----


@app.route('/buscar_nome', methods=['POST'])
def buscar_nome():
    """
    Busca o nome de um usuário na tabela 'login' pela matrícula.
    Usado para preencher o campo nome automaticamente no formulário de login.
    """
    data = request.get_json()
    matricula = data.get('matricula')
    if not matricula:
        return jsonify({'erro': 'Número de registro não informado'}), 400
    with app.app_context():
        usuario = db.session.query(Login.nome).filter_by(matricula=matricula).first()
    if usuario and usuario.nome:
        return jsonify({'nome': usuario.nome.title()})
    else:
        return jsonify({'nome': None})

#Busca as cidades#
@app.route('/buscar_cidades')
def buscar_cidades():
    """
    Retorna uma lista de cidades que correspondem a um termo de busca (para autocomplete).
    """
    termo = request.args.get('termo', '').lower()
    with app.app_context():
        # Usando .ilike para busca case-insensitive no PostgreSQL
        cidades = db.session.query(Cidade.cidade).filter(Cidade.cidade.ilike(f'%{termo}%')).limit(10).all()
    return jsonify([c[0].title() for c in cidades])

# --- Início da Rota Status Motorista ---
@app.route('/status_motorista/<string:matricula>', methods=['GET'])
def status_motorista(matricula):
    """
    Renderiza a página de status do motorista, passando a matrícula.
    """
    print(f"DEBUG: /status_motorista/{matricula} - Rota acessada.")
    # Passa a matrícula para o template
    return render_template('status_motorista.html', matricula=matricula)

# --- Rota API para buscar o status do motorista pela matrícula (AJUSTADA) ---
from flask import request

@app.route('/api/status_registro_by_matricula/<string:matricula>', methods=['GET'])
def api_status_registro_by_matricula(matricula):
    print(f"DEBUG: /api/status_registro_by_matricula/{matricula} - Rota API acessada.")

    registro_id = request.args.get('registro_id')
    registro_encontrado = None
    tabela_origem = None

    with app.app_context():
        if registro_id:
            try:
                registro_id_int = int(registro_id)
                # Tenta buscar o registro pelo ID
                registro_encontrado = db.session.query(Registro).filter_by(id=registro_id_int).first()
                if registro_encontrado:
                    tabela_origem = 'registros'
                else:
                    registro_encontrado = db.session.query(NoShow).filter_by(id=registro_id_int).first()
                    if registro_encontrado:
                        tabela_origem = 'no_show'
            except ValueError:
                print(f"DEBUG: registro_id inválido: {registro_id}")
                return jsonify({'message': 'ID de registro inválido.'}), 400
        else:
            # Lógica para buscar o registro pela matrícula (último ativo ou qualquer um)
            registro_encontrado = db.session.query(Registro).filter(
                Registro.matricula == matricula,
                Registro.finalizada == 0,
                Registro.cancelado == 0
            ).order_by(Registro.data_hora_login.desc()).first()

            if registro_encontrado:
                tabela_origem = 'registros'
            else:
                registro_encontrado = db.session.query(Registro).filter(
                    Registro.matricula == matricula,
                    or_(Registro.finalizada == 1, Registro.cancelado == 1)
                ).order_by(Registro.data_hora_login.desc()).first()
                if registro_encontrado:
                    tabela_origem = 'registros'
                else:
                    registro_encontrado = db.session.query(NoShow).filter(
                        NoShow.matricula == matricula,
                        NoShow.finalizada == 0,
                        NoShow.cancelado == 0,
                        NoShow.transferred_to_registro_id.is_(None)
                    ).order_by(NoShow.data_hora_login.desc()).first()
                    if registro_encontrado:
                        tabela_origem = 'no_show'
                    else:
                        registro_encontrado = db.session.query(NoShow).filter(
                            NoShow.matricula == matricula,
                            or_(NoShow.finalizada == 1, NoShow.cancelado == 1, NoShow.em_separacao == 4)
                        ).order_by(NoShow.data_hora_login.desc()).first()
                        if registro_encontrado:
                            tabela_origem = 'no_show'

        if registro_encontrado:
            response_data = {
                'id': registro_encontrado.id,
                'nome': registro_encontrado.nome,
                'matricula': registro_encontrado.matricula,
                'finalizada': getattr(registro_encontrado, 'finalizada', 0),
                'cancelado': getattr(registro_encontrado, 'cancelado', 0),
                'em_separacao': getattr(registro_encontrado, 'em_separacao', 0),
                'gaiola': getattr(registro_encontrado, 'gaiola', None),
                'estacao': getattr(registro_encontrado, 'estacao', None),
                'rota': getattr(registro_encontrado, 'rota', None),
                'tipo_entrega': getattr(registro_encontrado, 'tipo_entrega', None),
                'cidade_entrega': getattr(registro_encontrado, 'cidade_entrega', None),
                'rua': getattr(registro_encontrado, 'rua', None),
                'data_hora_login': registro_encontrado.data_hora_login.strftime('%Y-%m-%d - %H:%M') if registro_encontrado.data_hora_login else None,
                'tabela_origem': tabela_origem,
                'estado': None
            }
            # ... (o resto da sua lógica de formatação da resposta) ...
            print(f"DEBUG: Registro encontrado: {response_data}")
            return jsonify(response_data)
        else:
            print(f"DEBUG: Nenhum registro encontrado para matrícula {matricula} e ID {registro_id}.")
            return jsonify({'message': 'Nenhum registro encontrado para esta matrícula e ID.'}), 404



def atualizar_status_registros_noshow():
    with app.app_context():
        registros_pendentes = Registro.query.filter(Registro.tipo_entrega == 'No-Show', Registro.em_separacao == 0).all()
        for registro in registros_pendentes:
            noshow_correspondente = NoShow.query.filter(
                NoShow.gaiola == registro.rota,
                NoShow.tipo_entrega == 'No-Show'
                # Adicione outras condições de filtro, se necessário
            ).first()
            if noshow_correspondente:
                registro.em_separacao = 2  # Exemplo de atualização de status
                db.session.commit()
                print(f"DEBUG: Registro ID {registro.id} atualizado devido a No-Show correspondente.")


REGISTROS_POR_PAGINA = 10 # Defina o número de registros por página
@app.route('/registros')
def registros():
    atualizar_status_registros_noshow() # type: ignore # Chama a função aqui

    page = request.args.get('pagina', 1, type=int)
    per_page = 10 # Quantidade de itens por página

    rota = request.args.get('rota')
    tipo_entrega = request.args.get('tipo_entrega')
    cidade = request.args.get('cidade')
    em_separacao = request.args.get('em_separacao') # <--- CAPTURA O FILTRO DE EM_SEPARACAO

    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')

    # Query inicial para todos os registros
    query = Registro.query

    # Aplica filtros opcionais
    if rota:
        query = query.filter(Registro.rota.ilike(f'%{rota}%'))
    if tipo_entrega:
        query = query.filter(Registro.tipo_entrega == tipo_entrega)
    if cidade:
        query = query.filter(Registro.cidade_entrega.ilike(f'%{cidade}%'))

    # Adiciona filtro por em_separacao, se fornecido
    if em_separacao:
        query = query.filter(Registro.em_separacao == int(em_separacao)) # <--- APLICA O FILTRO DE EM_SEPARACAO

    # Filtro por data
    if data_inicio_str:
        try:
            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d')
            query = query.filter(Registro.data_hora_login >= data_inicio)
        except ValueError:
            flash("Formato de data inicial inválido. Use💼-MM-DD.", 'danger')
            data_inicio_str = '' # Limpa para não preencher o campo no template
    if data_fim_str:
        try:
            # Inclui até o final do dia
            data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d') + timedelta(days=1) - timedelta(seconds=1)
            query = query.filter(Registro.data_hora_login <= data_fim)
        except ValueError:
            flash("Formato de data final inválido. Use💼-MM-DD.", 'danger')
            data_fim_str = '' # Limpa para não preencher o campo no template

    # Ordena os resultados (ex: mais recentes primeiro)
    query = query.order_by(Registro.data_hora_login.desc())

    # Paginação
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # Obtenha as cidades distintas para o filtro
    cidades_disponiveis = [c.cidade for c in Cidade.query.order_by(Cidade.cidade).all()]

    return render_template('registros.html',
                           registros=pagination.items,
                           pagina=pagination.page,
                           total_paginas=pagination.pages,
                           total_registros=pagination.total,
                           rota=rota or '',
                           tipo_entrega=tipo_entrega or '',
                           cidade=cidade or '',
                           em_separacao=em_separacao or '', # <--- PASSA O VALOR DE EM_SEPARACAO DE VOLTA PARA O TEMPLATE
                           data_inicio=data_inicio_str or '',
                           data_fim=data_fim_str or '',
                           cidades=cidades_disponiveis)

# --- NOVO ENDPOINT DE API PARA AJAX ---
@app.route('/api/registros_data')
def api_registros_data():
    page = request.args.get('pagina', 1, type=int)
    per_page = REGISTROS_POR_PAGINA

    rota = request.args.get('rota')
    tipo_entrega = request.args.get('tipo_entrega')
    cidade = request.args.get('cidade')
    em_separacao_filtro_str = request.args.get('em_separacao') # Valor string do filtro

    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')

    query = Registro.query # Inicia a query com seu modelo SQLAlchemy

    # Aplica filtros opcionais
    if rota:
        query = query.filter(Registro.rota.ilike(f'%{rota}%'))
    if tipo_entrega:
        query = query.filter(Registro.tipo_entrega == tipo_entrega)
    if cidade:
        query = query.filter(Registro.cidade_entrega.ilike(f'%{cidade}%'))

    # Lógica de filtro para em_separacao baseada nos valores enviados pelo JS:
    if em_separacao_filtro_str:
        if em_separacao_filtro_str == '0': # Aguardando Carregar
            query = query.filter(
                Registro.em_separacao == 0,
                Registro.finalizada == 0,
                Registro.cancelado == 0
            )
        elif em_separacao_filtro_str == '1': # Em Separação
            query = query.filter(
                Registro.em_separacao == 1,
                Registro.finalizada == 0,
                Registro.cancelado == 0
            )
        elif em_separacao_filtro_str == '2': # AGUARDANDO TRANSFERÊNCIA - ADICIONADO AQUI
            query = query.filter(
            Registro.em_separacao == 2,
            Registro.finalizada == 0,
            Registro.cancelado == 0
            )
        elif em_separacao_filtro_str == '3': # Finalizado (corresponde a finalizada = 1)
            query = query.filter(Registro.finalizada == 1)
        elif em_separacao_filtro_str == '4': # Cancelado (corresponde a cancelado = 1)
            query = query.filter(Registro.cancelado == 1)
    
    # Filtro por data
    if data_inicio_str:
        try:
            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d')
            query = query.filter(Registro.data_hora_login >= data_inicio)
        except ValueError:
            pass # Ignora, o JS não espera flash messages aqui
    if data_fim_str:
        try:
            # Inclui até o final do dia
            data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d') + timedelta(days=1) - timedelta(seconds=1)
            query = query.filter(Registro.data_hora_login <= data_fim)
        except ValueError:
            pass # Ignora

    query = query.order_by(Registro.data_hora_login.desc())

    # Paginação usando o paginate do SQLAlchemy
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # Converte os objetos Registro para um formato serializável em JSON
    # Isso é essencial para enviar os dados para o frontend.
    registros_json = []
    for reg in pagination.items:
        registros_json.append({
            'id': reg.id,
            'data_hora_login': reg.data_hora_login.strftime('%Y-%m-%d %H:%M:%S') if reg.data_hora_login else None,
            'nome': reg.nome,
            'matricula': reg.matricula,
            'rota': reg.rota,
            'tipo_entrega': reg.tipo_entrega,
            'cidade_entrega': reg.cidade_entrega,
            'hora_finalizacao': reg.hora_finalizacao.strftime('%Y-%m-%d %H:%M:%S') if reg.hora_finalizacao else None,
            'em_separacao': reg.em_separacao,
            'finalizada': reg.finalizada,
            'cancelado': reg.cancelado
        })

    return jsonify({
        'records': registros_json,
        'pagina': pagination.page,
        'total_paginas': pagination.pages,
        'total_registros': pagination.total
    })


#Fim da Rota Registros#
@app.route('/boas_vindas')
def boas_vindas():
    """Página de boas-vindas após login/cadastro."""
    return render_template('boas_vindas.html')

@app.route('/sucesso')
def sucesso():
    """Página de sucesso de cadastro."""
    return render_template('sucesso.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    """
    Handles initial user registration and records data in the login table.
    Prevents re-registering an existing matricula.
    """
    erro = None
    sucesso = None
    if request.method == 'POST':
        nome = request.form['nome'].title()
        matricula = request.form['matricula']
        tipo_veiculo = request.form['tipo_veiculo'].title()
        
        # AQUI É A MUDANÇA! Não use strptime, já é um datetime.
        data_cadastro_obj = get_data_hora_brasilia() 

        with app.app_context():
            # Verificar se a matrícula já existe na tabela login.
            existente_matricula = db.session.query(Login).filter_by(matricula=matricula).first()
            if existente_matricula:
                erro = "Número de registro já cadastrado. Por favor, tente fazer login."
                print(f"Cadastro falhou para o número de registro {matricula}: Número de registro já existe na tabela login.")
                return render_template('cadastro.html', erro=erro)

            # Inserir os novos dados do usuário na tabela login.
            new_login = Login(
                nome=nome, 
                matricula=matricula, 
                tipo_veiculo=tipo_veiculo,
                data_cadastro=data_cadastro_obj # Use o objeto datetime diretamente aqui
            )
            db.session.add(new_login)
            db.session.commit()

            print(f"Número de registro {matricula} cadastrado com sucesso na tabela login.")
            return redirect(url_for('sucesso'))

    return render_template('cadastro.html', erro=erro)


#Rota Associacao #
@app.route('/associacao')
def associacao():
    registro_id = request.args.get('id', type=int) # Tenta obter o ID da URL
    registros_para_exibir = []
    filtro_id_aplicado = False
    
    per_page = 10 # Define quantos registros por página se não for um ID específico
    page = request.args.get('pagina', 1, type=int) # Paginação para quando não há ID específico

    if registro_id:
        # >>>>>>>>>>> AQUI ESTÁ A MUDANÇA PRINCIPAL <<<<<<<<<<<
        # Substitua 'get_registro_by_id(registro_id)' por 'Registro.query.get(registro_id)'
        registro = Registro.query.get(registro_id)
        # >>>>>>>>>>> FIM DA MUDANÇA PRINCIPAL <<<<<<<<<<<

        if registro:
            # Apenas adiciona se não estiver finalizado
            if registro.finalizada == 0:
                registros_para_exibir.append(registro)
            else:
                flash(f'O registro com ID {registro_id} já foi finalizado e não pode ser editado.', 'warning')
        else:
            flash(f'Registro com ID {registro_id} não encontrado.', 'danger')
        filtro_id_aplicado = True # Sinaliza que um ID específico foi procurado
        
        # Para um único registro, a paginação é sempre 1/1
        pagina = 1
        total_paginas = 1
    else:
        # Se nenhum ID foi passado, mostra os registros que estão 'prontos' para serem associados/finalizados.
        query = Registro.query.filter(Registro.finalizada == 0, Registro.cancelado == 0)
        query = query.filter(Registro.em_separacao.in_([0, 1, 2])) 
        
        query = query.order_by(Registro.data_hora_login.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        registros_para_exibir = pagination.items
        pagina = pagination.page
        total_paginas = pagination.pages


    return render_template('associacao.html',
                           registros=registros_para_exibir,
                           filtro_id=registro_id if filtro_id_aplicado else None,
                           pagina=pagina,
                           total_paginas=total_paginas,
                           rota=request.args.get('rota', ''),
                           tipo_entrega=request.args.get('tipo_entrega', '')
                          )


## --- ROTA API para atualizar o status em_separacao ---
@app.route('/api/update_separacao_status/<int:registro_id>', methods=['POST'])
def api_update_separacao_status(registro_id):
    try:
        data = request.get_json()
        new_status = data.get('em_separacao_status') # Deve ser 1 para "Em Separação"

        if new_status is None:
            return jsonify({"error": "Status não fornecido."}), 400

        # Valide o status (0, 1, 2, 3) conforme sua lógica de negócios
        if not isinstance(new_status, int) or new_status not in [0, 1, 2, 3]:
            return jsonify({"error": "Status inválido. Deve ser 0, 1, 2 ou 3."}), 400

        # >>>>>>>>>>> AQUI ESTÁ A MUDANÇA PRINCIPAL <<<<<<<<<<<
        # Substitua qualquer chamada a 'get_registro_by_id' por Registro.query.get()
        registro = Registro.query.get(registro_id)
        # >>>>>>>>>>> FIM DA MUDANÇA PRINCIPAL <<<<<<<<<<<

        if not registro:
            return jsonify({"error": "Registro não encontrado."}), 404
        
        # Impede a atualização se o registro já estiver finalizado ou cancelado
        if registro.finalizada == 1 or registro.cancelado == 1:
            return jsonify({"error": "Este registro já foi finalizado ou cancelado e não pode ser atualizado."}), 400

        # Atualiza o status 'em_separacao'
        registro.em_separacao = new_status
        db.session.commit() # Salva a mudança no banco de dados

        return jsonify({"message": f"Status do registro {registro_id} atualizado para {new_status} (Em Separação).", "status": new_status}), 200

    except Exception as e:
        # Registra o erro para depuração (opcional, mas recomendado)
        app.logger.error(f"Erro ao atualizar status de separação para registro {registro_id}: {e}")
        return jsonify({"error": "Ocorreu um erro interno ao processar a requisição."}), 500



# Rota para associar/salvar gaiola/estacao
# app.py

@app.route('/associar_id/<int:id>', methods=['POST'])
def associar_id(id):
    registro = Registro.query.get(id) 
    
    if not registro:
        return jsonify({"error": "Registro não encontrado."}), 404
    
    # Adicionando verificação para registros já finalizados ou cancelados
    # Usamos agora o status em_separacao para verificar isso
    if registro.em_separacao == 3 or registro.em_separacao == 4: # 3=Finalizado, 4=Cancelado
        return jsonify({"error": "Registro já está finalizado ou cancelado e não pode ser associado."}), 400

    gaiola = request.form.get('gaiola')
    estacao = request.form.get('estacao')
    rua = request.form.get('rua') # Para No-Show

    # Atualiza os campos
    registro.gaiola = gaiola
    registro.estacao = estacao
    
    if registro.tipo_entrega == 'No-Show':
        registro.rua = rua
    
    # Se o registro está em 'Aguardando Carregamento' (0) ou 'Em Separação' (1) e foi "salvo" com os dados,
    # ele agora passa para 'Carregamento Liberado' (2).
    # Esta é a principal mudança aqui.
    if registro.em_separacao in [0, 1]: 
        registro.em_separacao = 2 # Define como Carregamento Liberado
    
    db.session.commit()

    return jsonify({"message": "Associação salva e Carregamento Liberado!"}), 200

# ... (Mantenha as outras rotas exatamente como te passei na última vez:
#     /marcar_como_finalizado_id/<int:id>
#     /desassociar_id/<int:id>
#     /finalizar_carregamento_id_status_separacao/<int:id>
#     /carregar_no_show/<int:id>
# ) ...


@app.route('/desassociar_id/<int:id>', methods=['POST'])
def desassociar_id(id):
    registro = Registro.query.get(id)
    if not registro:
        return jsonify({"error": "Registro não encontrado."}), 404

    # Verifica se o registro já foi finalizado ou cancelado
    # Usamos agora o status em_separacao para verificar isso
    if registro.em_separacao == 3 or registro.em_separacao == 4: # 3=Finalizado, 4=Cancelado
        return jsonify({"error": "Não é possível desassociar um registro finalizado ou cancelado."}), 400
    
    # Reseta os campos de associação
    registro.gaiola = None
    registro.estacao = None
    if registro.tipo_entrega == 'No-Show':
        registro.rua = None
    
    # Define em_separacao de volta para 1 (Em Separação)
    # Se estava em 2 (Carregamento Liberado), volta para 1
    registro.em_separacao = 1 
    
    db.session.commit()
    
    return jsonify({"message": "Registro desassociado e retornado para 'Em Separação'!"}), 200


@app.route('/marcar_como_finalizado_id/<int:id>', methods=['POST'])
def marcar_como_finalizado_id(id):
    registro = Registro.query.get(id)
    if not registro:
     return jsonify({"error": "Registro não encontrado."}), 404

    print(f"DEBUG: Tentando finalizar registro ID {id}, finalizada={registro.finalizada}, cancelado={registro.cancelado}") # Adicione esta linha

    if registro.finalizada == 1 or registro.cancelado == 1:
     return jsonify({"error": "O registro já está finalizado ou cancelado."}), 400

    registro.finalizada = 1
    registro.em_separacao = 3
    registro.hora_finalizacao = get_data_hora_brasilia()

    db.session.commit()
    return jsonify({"message": "Registro finalizado com sucesso!"}), 200
# app.py

@app.route('/cancelar_registro/<int:id>', methods=['POST'])
def cancelar_registro(id):
    registro = Registro.query.get(id)
    if not registro:
        return jsonify({"error": "Registro não encontrado."}), 404

    # Adicionando verificação para evitar cancelar registros já finalizados ou cancelados
    if registro.em_separacao == 3 or registro.em_separacao == 4:
        return jsonify({"error": "Registro já está finalizado ou cancelado."}), 400

    registro.em_separacao = 4  # Define como Cancelado (status 4)
    # Opcional: Você pode manter registro.cancelado = 1 se for útil para outros relatórios/filtros
    # ou remover esta linha se em_separacao for a única fonte da verdade para o status final.
    registro.cancelado = 1
    
    db.session.commit()
    
    return jsonify({"message": "Registro cancelado com sucesso!"}), 200


@app.route('/finalizar_carregamento_id_status_separacao/<int:id>', methods=['POST'])
def finalizar_carregamento_id_status_separacao(id):
    registro = get_registro_by_id(id)
    if not registro or registro.get('finalizada') == 1:
        flash('Registro não encontrado ou já finalizado.', 'danger')
        return redirect(url_for('associacao'))

    # Define em_separacao para 2 (Carregamento Concluído)
    # Ex: registro.em_separacao = 2
    # db.session.commit()
    print(f"DEBUG: Marcando carregamento como concluído para registro ID {id}. Setando em_separacao=2")
    registro['em_separacao'] = 2

    flash('Carregamento marcado como concluído!', 'info')
    return redirect(url_for('associacao', id=id))


# ---- Rotas No Show ----

# --- Sua Rota '/registro_no_show' Atualizada ---
# app.py

# ... (seus imports, definições de STATUS_EM_SEPARACAO, get_status_text, e o modelo NoShow) ...

@app.route('/registro_no_show', methods=['GET'])
def registro_no_show():
    data_filtro_str = request.args.get('data')
    nome_filtro = request.args.get('nome')
    matricula_filtro = request.args.get('matricula')
    rota_filtro = request.args.get('rota')
    status_filtro_str = request.args.get('status')
    pagina = request.args.get('pagina', 1, type=int)
    por_pagina = 10

    query = NoShow.query

    if data_filtro_str:
        try:
            data_inicio = datetime.strptime(data_filtro_str, '%Y-%m-%d')
            data_fim = data_inicio + timedelta(days=1) - timedelta(microseconds=1)
            query = query.filter(NoShow.data_hora_login.between(data_inicio, data_fim))
        except ValueError:
            flash("Formato de data inválido. Use AAAA-MM-DD.", "error")
            data_filtro_str = None

    if nome_filtro:
        query = query.filter(NoShow.nome.ilike(f'%{nome_filtro}%'))

    if matricula_filtro:
        query = query.filter(NoShow.matricula.ilike(f'%{matricula_filtro}%'))

    if rota_filtro:
        query = query.filter(NoShow.gaiola.ilike(f'%{rota_filtro}%'))

    if status_filtro_str:
        if status_filtro_str == 'aguardando_motorista':
            query = query.filter(NoShow.em_separacao == STATUS_EM_SEPARACAO['AGUARDANDO_MOTORISTA'])
        elif status_filtro_str == 'separacao':
            query = query.filter(NoShow.em_separacao == STATUS_EM_SEPARACAO['SEPARACAO'])
        elif status_filtro_str == 'finalizado':
            query = query.filter(or_(
                NoShow.em_separacao == STATUS_EM_SEPARACAO['FINALIZADO'],
                NoShow.finalizada == 1
            ))
        elif status_filtro_str == 'cancelado':
            query = query.filter(or_(
                NoShow.em_separacao == STATUS_EM_SEPARACAO['CANCELADO'],
                NoShow.cancelado == 1
            ))
        elif status_filtro_str == 'transferido':
            query = query.filter(NoShow.em_separacao == STATUS_EM_SEPARACAO['TRANSFERIDO'])

    query = query.order_by(NoShow.data_hora_login.desc())

    paginated_results = query.paginate(page=pagina, per_page=por_pagina, error_out=False)
    registros_no_show = paginated_results.items
    total_paginas = paginated_results.pages

    return render_template('registro_no_show.html',
                           registros_no_show=registros_no_show,
                           data_filtro=data_filtro_str,
                           nome_filtro=nome_filtro,
                           matricula_filtro=matricula_filtro,
                           rota_filtro=rota_filtro,
                           status_filtro=status_filtro_str,
                           pagina=pagina,
                           total_paginas=total_paginas,
                           get_status_text=get_status_text,
                           # ESTA É A LINHA CORRETA:
                           STATUS_EM_SEPARACAO=STATUS_EM_SEPARACAO # <-- Esta é a forma correta!
                           )


# --- ROTA UNIFICADA: Atualizar Status (para Associar, Finalizar, Cancelar, Transferir) ---
# Esta rota substituirá a lógica de 'marcar_como_finalizado_no_show_id', 'associar_no_show_id' e 'transferir_no_show_para_registro'
@app.route('/atualizar_status_no_show/<int:registro_id>', methods=['POST'])
def atualizar_status_no_show(registro_id):
    registro = NoShow.query.get_or_404(registro_id)
    novo_status_code_str = request.form.get('novo_status')

    # Capturar dados do formulário de associação, se existirem
    gaiola = request.form.get('gaiola')
    estacao = request.form.get('estacao')
    rua = request.form.get('rua')

    try:
        novo_status_code = int(novo_status_code_str)

        # Validar se o novo_status_code é um dos valores permitidos
        if novo_status_code not in STATUS_EM_SEPARACAO.values():
            flash("Código de status inválido.", 'error')
            return redirect(url_for('registro_no_show', _anchor=f'registro-{registro_id}'))

        # Lógica para "Associar" (quando o status vai para AGUARDANDO_MOTORISTA = 0)
        if novo_status_code == STATUS_EM_SEPARACAO['AGUARDANDO_MOTORISTA']:
            if not gaiola or not estacao or not rua:
                flash("Rota, Estação e Rua são obrigatórios para associar.", 'error')
                return redirect(url_for('registro_no_show', _anchor=f'registro-{registro_id}'))

            registro.gaiola = gaiola
            registro.estacao = estacao
            registro.rua = rua
            registro.em_separacao = STATUS_EM_SEPARACAO['AGUARDANDO_MOTORISTA']
            registro.hora_finalizacao = None
            registro.finalizada = 0
            registro.cancelado = 0
            flash(f"Registro No-Show #{registro_id} associado e aguardando motorista.", 'success')

        # Lógica para 'Cancelar' (3)
        elif novo_status_code == STATUS_EM_SEPARACAO['CANCELADO']:
            registro.em_separacao = novo_status_code
            registro.cancelado = 1
            registro.finalizada = 0
            registro.hora_finalizacao = datetime.now()
            flash(f"Registro No-Show #{registro_id} cancelado com sucesso!", 'success')

        # Lógica para 'Finalizar' (2)
        elif novo_status_code == STATUS_EM_SEPARACAO['FINALIZADO']:
            registro.em_separacao = novo_status_code
            registro.finalizada = 1
            registro.cancelado = 0
            registro.hora_finalizacao = datetime.now()
            flash(f"Registro No-Show #{registro_id} finalizado com sucesso!", 'success')

        # --- Lógica para 'Transferir' (4) ---
        elif novo_status_code == STATUS_EM_SEPARACAO['TRANSFERIDO']:
            try:
                print(f"\n--- INÍCIO DA TRANSFERÊNCIA PARA O REGISTRO NoShow ID: {registro_id} ---")
                print(f"Dados do NoShow (para busca no Registros):")
                print(f"  Gaiola (Rota no Registros): '{registro.gaiola}'")
                print(f"  Estacao (Cidade de Entrega no Registros): '{registro.estacao}'")

                # **PASSO 1: ENCONTRAR E TENTAR FINALIZAR O REGISTRO PRINCIPAL NO REGISTROS**
                registro_principal_a_finalizar = Registros.query.filter_by(
                    rota=registro.gaiola,
                    cidade_entrega=registro.estacao,
                    tipo_entrega='No-Show',
                    finalizada=0
                ).first()

                if registro_principal_a_finalizar:
                    print(f"ACHOU O REGISTRO PRINCIPAL! ID: {registro_principal_a_finalizar.id}")
                    print(f"Status atual do Registro Principal: Finalizada={registro_principal_a_finalizar.finalizada}, Tipo de Entrega={registro_principal_a_finalizar.tipo_entrega}")

                    # ATUALIZAÇÃO E COMMIT IMEDIATO DO REGISTRO PRINCIPAL
                    registro_principal_a_finalizar.finalizada = 1  # <--- Marcar finalizada como 1
                    registro_principal_a_finalizar.hora_finalizacao = datetime.now()
                    db.session.add(registro_principal_a_finalizar)
                    db.session.commit() # Commit para garantir que esta alteração seja salva AGORA

                    print(f"Registro Principal ID {registro_principal_a_finalizar.id} ATUALIZADO: finalizada=1.")
                    flash(f"Registro No-Show #{registro_id} processado. **Registro principal (ID: {registro_principal_a_finalizar.id}) FINALIZADO** com sucesso.", 'success')

                else:
                    print(f"NÃO ENCONTRADO! Nenhum registro principal correspondente em 'Registros'.")
                    print(f"Verifique se existe um registro em 'Registros' com:")
                    print(f"  rota='{registro.gaiola}'")
                    print(f"  cidade_entrega='{registro.estacao}'")
                    print(f"  tipo_entrega='No-Show'")
                    print(f"  finalizada=0")
                    flash(f"Aviso: Não foi possível encontrar o registro principal em Registros para finalizar. Verifique os dados.", 'warning')

                # **PASSO 2: ATUALIZAR O REGISTRO NOSHOW**
                # Esta parte será commitada separadamente
                registro.em_separacao = novo_status_code  # Marcar como TRANSFERIDO (4)
                registro.finalizada = 1                   # NoShow também finalizado
                registro.hora_finalizacao = datetime.now()
                db.session.add(registro)
                db.session.commit() # Commit para as alterações no NoShow

                print(f"Registro NoShow ID {registro_id} atualizado para TRANSFERIDO e finalizado.")
                print(f"--- FIM DA TRANSFERÊNCIA PARA O REGISTRO NoShow ID: {registro_id} ---\n")

                return redirect(url_for('registro_no_show', _anchor=f'registro-{registro_id}'))

            except Exception as e:
                db.session.rollback() # Desfaz qualquer coisa caso haja um erro grave
                flash(f"Erro ao transferir Registro No-Show #{registro_id}: {str(e)}", 'error')
                print(f"ERRO CRÍTICO NA TRANSFERÊNCIA: {str(e)}")
                print(f"--- FIM DA TRANSFERÊNCIA COM ERRO PARA O REGISTRO NoShow ID: {registro_id} ---\n")
                return redirect(url_for('registro_no_show', _anchor=f'registro-{registro_id}'))
        # --- FIM DA LÓGICA DE TRANSFERÊNCIA ---

        # Lógica para outros status (não 'TRANSFERIDO')
        db.session.commit() # Commit para os outros status

    except ValueError:
        flash("Status inválido ou dados de associação incompletos.", 'error')
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao atualizar status do registro: {str(e)}", 'error')

    # Redireciona de volta para a página de registros, mantendo o filtro e focando no registro
    return redirect(url_for('registro_no_show', _anchor=f'registro-{registro_id}',
                             data=request.args.get('data'),
                             nome=request.args.get('nome'),
                             matricula=request.args.get('matricula'),
                             rota=request.args.get('rota'),
                             status=request.args.get('status')))


@app.route('/dessociar_no_show/<int:registro_id>', methods=['POST'])
def dessociar_no_show(registro_id):
    registro = NoShow.query.get_or_404(registro_id)

    try:
        # 1. Limpa os dados de Rota, Estação e Rua
        registro.gaiola = None
        registro.estacao = None
        registro.rua = None

        # 2. Muda o status em_separacao para 1 (SEPARACAO)
        registro.em_separacao = STATUS_EM_SEPARACAO['SEPARACAO']
        registro.hora_finalizacao = None # Se for dessassociado, não está mais finalizado

        # Limpa os campos legados de finalizado/cancelado se estiverem ativos
        registro.finalizada = 0
        registro.cancelado = 0

        db.session.commit()
        flash(f"Registro No-Show #{registro_id} dessassociado e em separação.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao dessassociar registro: {str(e)}", 'error')

    # Redireciona de volta para a página de registros, mantendo o filtro e focando no registro
    return redirect(url_for('registro_no_show', _anchor=f'registro-{registro_id}',
                             data=request.args.get('data'),
                             nome=request.args.get('nome'),
                             matricula=request.args.get('matricula'),
                             rota=request.args.get('rota'),
                             status=request.args.get('status')))

@app.route('/cancelar_no_show/<int:id>', methods=['POST'])
def cancelar_no_show(id):
    no_show = NoShow.query.get(id)
    if not no_show:
        return jsonify({"error": "Registro No-Show não encontrado."}), 404
    # Coloque a linha de print AQUI:
    print(f"DEBUG: Tentando cancelar registro No-Show ID {id}, em_separacao={no_show.em_separacao}")


    if no_show.em_separacao in [3, 4]:
        return jsonify({"error": "Registro No-Show já está finalizado ou cancelado."}), 400

    no_show.em_separacao = 3  # Define como Cancelado (status 3) na tabela no_show
    no_show.hora_finalizacao = datetime.now(pytz.timezone('America/Sao_Paulo')) # Registra a hora atual de Brasília

    db.session.commit()

    return jsonify({"message": "Registro No-Show cancelado com sucesso!"}), 200

@app.route('/finalizar_carregamento_no_show_id_status_separacao/<int:id>', methods=['POST'])
def finalizar_carregamento_no_show_id_status_separacao(id):
    registro = NoShow.query.get(id)
    if registro:
        # Se 'em_separacao' == 1 (Em Separação), muda para 2 (Aguardando Entregador)
        if registro.em_separacao == 1:
            registro.em_separacao = 2
            db.session.commit()
            flash('Status do registro No-Show alterado para Aguardando Entregador!', 'success')
        else:
            flash('Registro não está no status "Em Separação" para aguardar entregador.', 'warning')
    else:
        flash('Registro No-Show não encontrado.', 'error')
    return redirect(url_for('registro_no_show', _anchor=f'no-show-registro-{id}'))


@app.route('/registros', methods=['GET', 'POST'])
def criar_registro_principal():
    if request.method == 'POST':
        print(f"DEBUG_REG_CRIAR: [Passo 1] Rota de criação acessada via POST!")
        print(f"DEBUG_REG_CRIAR: [Passo 1.1] Conteúdo do formulário: {request.form}")

        nome = request.form.get('nome')
        matricula = request.form.get('matricula')
        # >>> MUDANÇA AQUI: use data_hora_login para o argumento
        data_hora_login_agora = datetime.now() # Renomeado para evitar confusão

        rota_input = request.form.get('rota')
        tipo_entrega = request.form.get('tipo_entrega')
        cidade_entrega = request.form.get('cidade_entrega')

        novo_registro = Registro(
            nome=nome,
            matricula=matricula,
            # >>> MUDANÇA AQUI: Passe para data_hora_login
            data_hora_login=data_hora_login_agora, # <--- Corrigido aqui!
            rota=rota_input,
            tipo_entrega=tipo_entrega,
            cidade_entrega=cidade_entrega,
            rua='Aguarde',
            estacao_carregamento='Aguarde',
            status=STATUS_REGISTRO_PRINCIPAL['AGUARDANDO_CARREGAMENTO']
        )

        if tipo_entrega == 'No-Show':
            print(f"DEBUG_REG_CRIAR: [Passo 2] Tipo de entrega é 'No-Show'. Tentando buscar NoShow.")
            print(f"DEBUG_REG_CRIAR: [Passo 2.1] Buscando NoShow com Gaiola LIKE '{rota_input}' e em_separacao = {STATUS_EM_SEPARACAO['SEPARACAO']}")

            no_show_encontrado = NoShow.query.filter(
                NoShow.gaiola.ilike(rota_input),
                NoShow.em_separacao == STATUS_EM_SEPARACAO['SEPARACAO']
            ).first()

            if no_show_encontrado:
                print(f"DEBUG_REG_CRIAR: [Passo 3] SUCESSO! NoShow encontrado: ID={no_show_encontrado.id}, Gaiola='{no_show_encontrado.gaiola}', Rua='{no_show_encontrado.rua}', Estacao='{no_show_encontrado.estacao}', Em_Separacao={no_show_encontrado.em_separacao}")

                novo_registro.rota = no_show_encontrado.gaiola
                novo_registro.rua = no_show_encontrado.rua
                novo_registro.estacao_carregamento = no_show_encontrado.estacao
                novo_registro.status = STATUS_REGISTRO_PRINCIPAL['CARREGAMENTO_LIBERADO']
                novo_registro.em_separacao = no_show_encontrado.em_separacao

                flash(f"Registro criado! Rota '{rota_input}' do tipo No-Show associado a um carregamento liberado.", 'success')

                # Atualiza o NoShow encontrado para evitar duplicidade
                no_show_encontrado.em_separacao = STATUS_EM_SEPARACAO['AGUARDANDO_ENTREGADOR']
                db.session.add(no_show_encontrado)

            else:
                print(f"DEBUG_REG_CRIAR: [Passo 3] FALHA! Nenhum NoShow correspondente encontrado para Rota '{rota_input}' com status 'SEPARACAO'.")
                flash(f"Registro criado! Rota '{rota_input}' do tipo No-Show aguardando associação de carregamento.", 'warning')
                novo_registro.status = STATUS_REGISTRO_PRINCIPAL['AGUARDANDO_CARREGAMENTO']
                novo_registro.em_separacao = None
        else:
            print(f"DEBUG_REG_CRIAR: [Passo 2] Tipo de entrega '{tipo_entrega}' não é 'No-Show'. Não buscar NoShow.")
            novo_registro.status = STATUS_REGISTRO_PRINCIPAL['AGUARDANDO_CARREGAMENTO']
            novo_registro.em_separacao = None

        db.session.add(novo_registro)
        db.session.commit()
        flash("Registro de chegada criado com sucesso!", 'success')
        return redirect(url_for('alguma_pagina_apos_registro'))

    return render_template('seu_template_de_registro.html', erro=None)

    # Lógica para requisições GET (exibir o formulário)
from sqlalchemy import or_

@app.route('/transferir_no_show_para_registro/<int:no_show_id>', methods=['POST'])
def transferir_no_show_para_registro(no_show_id):
    no_show_original = NoShow.query.get_or_404(no_show_id)

    try:
        # 2. BUSCAR O REGISTRO CORRESPONDENTE NA TABELA 'REGISTROS' (DESTINO)
        registro_principal_correspondente = Registro.query.filter(
            Registro.rota == no_show_original.gaiola.strip(),
            Registro.tipo_entrega == 'No-Show',
            or_(Registro.estacao.is_(None), Registro.estacao == no_show_original.estacao.strip())
        ).first()

        flash_msg_registro = ""

        if registro_principal_correspondente:
            # 1. ATUALIZAR O REGISTRO NO-SHOW (ORIGEM)
            # Marca o NoShow original como 'TRANSFERIDO'
            no_show_original.em_separacao = STATUS_EM_SEPARACAO['TRANSFERIDO'] # Status 4
            no_show_original.hora_finalizacao = datetime.now() # Registra a hora da transferência
            db.session.add(no_show_original)

            # 3. TRANSFERIR OS DADOS DO NO_SHOW PARA O REGISTRO
            registro_principal_correspondente.gaiola = no_show_original.gaiola.strip().upper() # Transferir Rota para Gaiola
            registro_principal_correspondente.rua = no_show_original.rua.strip() # Transferir Rua
            registro_principal_correspondente.estacao = no_show_original.estacao.strip() # Atualizar a estação com o valor do No-Show
            registro_principal_correspondente.em_separacao = 3 # Mudar o valor de em_separacao para 3

            db.session.add(registro_principal_correspondente)
            flash_msg_registro = f" Dados do No-Show transferidos para o registro da rota '{no_show_original.gaiola}'."
            db.session.commit() # Salva as alterações em ambos os objetos
        else:
            # Caso não encontre um Registro principal correspondente
            print(f"ATENÇÃO: Nenhum Registro correspondente encontrado para NoShow ID {no_show_id} (Rota: {no_show_original.gaiola}, Estação (No-Show): {no_show_original.estacao}, Estação (Registro): NULL).")
            flash_msg_registro = f" Nenhum registro de carregamento correspondente encontrado para o No-Show da rota '{no_show_original.gaiola}' e estação '{no_show_original.estacao}'."

        flash(f"Registro No-Show #{no_show_id} transferido para carregamento." + flash_msg_registro, 'success')
        return redirect(url_for('registro_no_show', _anchor=f'no-show-registro-{no_show_id}',
                                                data=request.args.get('data'),
                                                nome=request.args.get('nome'),
                                                matricula=request.args.get('matricula'),
                                                rota=request.args.get('rota'),
                                                status=request.args.get('status')))

    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao transferir registro No-Show #{no_show_id}: {str(e)}", 'error')
        return redirect(url_for('registro_no_show', _anchor=f'no-show-registro-{no_show_id}',
                                                data=request.args.get('data'),
                                                nome=request.args.get('nome'),
                                                matricula=request.args.get('matricula'),
                                                rota=request.args.get('rota'),
                                                status=request.args.get('status')))
# ---- Criar Registro No Show ----

@app.route('/associacao_no_show', methods=['GET'])
def associacao_no_show():
    # Esta rota simplesmente renderiza o formulário
    return render_template('associacao_no_show.html')

@app.route('/criar_registro_no_show', methods=['POST'])
def criar_registro_no_show():
    nome = capitalize_words(request.form.get('nome'))
    data = request.form

    nome = data.get('nome')
    matricula = data.get('matricula')
    cidade_entrega = data.get('cidade_entrega')
    tipo_entrega = data.get('tipo_entrega')
    rota = data.get('rota').upper() if data.get('rota') else None  # <-- Aqui transforma em maiúsculo
    estacao = data.get('estacao')
    rua = data.get('rua')

    if not all([nome, matricula, tipo_entrega, rota, estacao, rua]):
        flash('Todos os campos obrigatórios devem ser preenchidos.', 'error')
        return redirect(url_for('associacao_no_show'))

    if not (rua.isdigit() and 1 <= int(rua) <= 9):
        flash('O campo "Rua" deve ser um dígito de 1 a 9.', 'error')
        return redirect(url_for('associacao_no_show'))

    try:
        novo_registro = NoShow(
            data_hora_login=datetime.now(),
            nome=nome,
            matricula=matricula,
            gaiola=rota,
            tipo_entrega=tipo_entrega,
            rua=rua,
            estacao=estacao,
            finalizada=0,
            cancelado=0,
            em_separacao=0
        )

        db.session.add(novo_registro)
        db.session.commit()

        flash('Registro No Show criado com sucesso!', 'success')
        return redirect(url_for('associacao_no_show'))

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Erro ao criar registro No Show: {e}")
        flash('Erro interno ao criar registro.', 'error')
        return redirect(url_for('associacao_no_show'))
    
    # No seu app.py


@app.route('/transferir_para_carregamento_no_show/<int:registro_id>', methods=['POST'])
def transferir_para_carregamento_no_show(registro_id):
    no_show_original = NoShow.query.get_or_404(registro_id)
    print(f"Tentando transferir No-Show ID: {registro_id}, Gaiola: {no_show_original.gaiola}")

    try:
        registro_principal = Registros.query.filter_by(
            rota=no_show_original.gaiola,
            tipo_entrega='No-Show',
            finalizada=0
        ).first()

        if registro_principal:
            print(f"Registro PRINCIPAL encontrado: ID {registro_principal.id}")
            registro_principal.finalizada = 1
            db.session.add(registro_principal)

            no_show_original.em_separacao = STATUS_EM_SEPARACAO['TRANSFERIDO']
            no_show_original.hora_finalizacao = datetime.now()
            db.session.add(no_show_original)

            db.session.commit()
            flash(f"Registro No-Show #{registro_id} transferido para carregamento com sucesso.", 'success')
        else:
            print("Nenhum registro PRINCIPAL correspondente encontrado.")
            flash(f"❌ Nenhum registro de carregamento correspondente encontrado para a rota '{no_show_original.gaiola}' e estação '{no_show_original.estacao}'.", 'error')

        return redirect(url_for('registro_no_show', status='aguardando_motorista'))

    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao transferir Registro No-Show #{registro_id}: {str(e)}", 'error')
        return redirect(url_for('registro_no_show', status='aguardando_motorista'))


@app.route('/finalizar_no_show/<int:id>', methods=['POST'])
def finalizar_no_show(id):
    """Função para finalizar um registro No Show e atualizar o registro correspondente em Registros."""
    no_show_original = NoShow.query.get_or_404(id)

    try:
        no_show_original.finalizada = 1
        no_show_original.hora_finalizacao = datetime.now()
        db.session.add(no_show_original)

        # Buscar o registro correspondente na tabela 'Registros'
        registro_principal_correspondente = Registro.query.filter(
            Registro.rota == no_show_original.gaiola.strip(),
            Registro.tipo_entrega == 'No-Show',
            or_(Registro.estacao.is_(None), Registro.estacao == no_show_original.estacao.strip())
        ).first()

        if registro_principal_correspondente:
            registro_principal_correspondente.finalizada = 1
            registro_principal_correspondente.hora_finalizacao = datetime.now()
            db.session.add(registro_principal_correspondente)

        db.session.commit()
        flash(f'Registro No Show com ID {id} foi finalizado e o registro correspondente em Registros foi atualizado (se encontrado)!', 'success')
        return redirect(url_for('registro_no_show', _anchor=f'no-show-registro-{id}'))

    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao finalizar registro No-Show #{id} ou atualizar o registro correspondente: {str(e)}", 'error')
        return redirect(url_for('registro_no_show', _anchor=f'no-show-registro-{id}'))
    
@app.route('/midia')
def exibir_midia():
    """Renderiza a página HTML com a exibição de mídia (vídeos e slides)."""
    print("DEBUG: Rota /midia acessada. Renderizando midia.html")
    return render_template('midia.html')

# --- Rota para exibir o menu principal ---
@app.route('/menu_principal')
def menu_principal():
    """Renderiza a página do menu principal."""
    print("DEBUG: /menu_principal - Rota acessada.")
    return render_template('menu_principal.html')




# ------ Painel Final - Fila de atendimento ------
# Agora acessível via /painel_final
@app.route('/painel_final')
def painel_final_page():
    """Renderiza a página do Painel de Atendimento."""
    return render_template('painel_final.html')


# --- Rota da API para Registros 'Em Separação' (Quadro 1) ---
# --- Rota da API para Registros 'Em Separação' (Quadro 1) ---
@app.route('/api/registros/em-separacao')
def get_registros_em_separacao():
    try:
        # Busca registros com 'em_separacao' igual a 1 (Em Separação)
        # e que não estão finalizados nem cancelados
        registros_em_separacao = Registro.query.filter(
            Registro.em_separacao == 2,
            Registro.finalizada == 0,
            Registro.cancelado == 0
        ).order_by(Registro.data_hora_login.asc()).all() # Ordena do mais antigo para o mais novo

        registros_json = []
        for reg in registros_em_separacao:
            registros_json.append({
                'id': reg.id,
                'nome': reg.nome,
                'matricula': reg.matricula,
                'rota': reg.rota,
                'tipo_entrega': reg.tipo_entrega,
                'cidade_entrega': reg.cidade_entrega,
                # Garante que as datas sejam serializadas para string
                'data_hora_login': reg.data_hora_login.strftime('%H:%M') if reg.data_hora_login else None,
                'gaiola': reg.gaiola if reg.gaiola else 'Aguardando',
                'estacao': reg.estacao if reg.estacao else 'Aguardando',
                'em_separacao_status': reg.em_separacao # Para depuração, se necessário
            })
        return jsonify(registros_json)
    except Exception as e:
        app.logger.error(f"Erro ao buscar registros 'Em Separação': {e}")
        return jsonify({"error": "Erro interno do servidor ao buscar registros 'Em Separação'."}), 500

# --- Rota da API para Rotas No-Show (Quadro 2) ---
@app.route('/api/noshow/aguardando-motorista')
def get_noshow_aguardando_motorista():
    try:
        # Busca registros NoShow com 'em_separacao' igual a 0 (Aguardando Motorista)
        # e que não estão finalizados nem cancelados
        noshow_aguardando = NoShow.query.filter(
            NoShow.em_separacao == 0,
            NoShow.finalizada == 0,
            NoShow.cancelado == 0
        ).order_by(NoShow.data_hora_login.asc()).all() # Ordena do mais antigo para o mais novo

        noshow_json = []
        for ns in noshow_aguardando:
            noshow_json.append({
                'id': ns.id,
                'nome': ns.nome,
                'matricula': ns.matricula,
                'gaiola': ns.gaiola, # 'gaiola' em NoShow corresponde à 'rota' principal
                'tipo_entrega': ns.tipo_entrega,
                'rua': ns.rua,
                'estacao': ns.estacao,
                # Garante que as datas sejam serializadas para string
                'data_hora_login': ns.data_hora_login.strftime('%H:%M') if ns.data_hora_login else None,
                'em_separacao_status': ns.em_separacao # Para depuração, se necessário
            })
        return jsonify(noshow_json)
    except Exception as e:
        app.logger.error(f"Erro ao buscar rotas No-Show Aguardando Motorista: {e}")
        return jsonify({"error": "Erro interno do servidor ao buscar rotas No-Show."}), 500

# --- Rota da API para Notícias (Letreiro Superior) ---

# --- ROTA AJUSTADA PARA BUSCAR NOTÍCIAS DA CNN BRASIL ---
@app.route('/api/get_news_headlines', methods=['GET'])
def get_news_headlines():
    # URL do feed RSS da CNN Brasil
    # Verificado em 2025-05-15, mas URLs de feed podem mudar.
    # Se parar de funcionar, pode ser necessário buscar a nova URL do feed RSS da CNN Brasil.
    cnn_brasil_feed_url = 'https://www.cnnbrasil.com.br/feed/'

    all_headlines = []

    # --- Buscar notícias da CNN Brasil (usando RSS) ---
    try:
        print(f"DEBUG Flask: Buscando feed da CNN Brasil em: {cnn_brasil_feed_url}")
        feed = feedparser.parse(cnn_brasil_feed_url)

        if feed.entries:
            print(f"DEBUG Flask: Feed da CNN Brasil encontrado com {len(feed.entries)} entradas.")
            # Limita o número de manchetes da CNN Brasil (ex: as 10 mais recentes)
            for entry in feed.entries[:10]: # Pega as 10 primeiras manchetes
                # Pode adicionar formatação ou limpar o título se necessário
                headline = entry.title
                # Exemplo: remover HTML básico se houver (feedparser geralmente limpa)
                # from bs4 import BeautifulSoup
                # headline = BeautifulSoup(headline, 'html.parser').get_text()

                all_headlines.append(f"CNN Brasil: {headline}") # Adiciona prefixo

        else:
            all_headlines.append("CNN Brasil: Não foi possível carregar manchetes do feed.")
            print("DEBUG Flask: Feed da CNN Brasil não retornou entradas.")

    except Exception as e:
        print(f"DEBUG Flask: Erro ao buscar feed da CNN Brasil: {e}")
        all_headlines.append("CNN Brasil: Erro ao carregar notícias.")

    # --- Seção para outras fontes (como Shopee) ---
    # Mantenha ou remova esta seção dependendo se você quer incluir outras fontes aqui.
    # Se você remover, o letreiro superior só mostrará a CNN Brasil.
    # Se você quiser adicionar outras fontes, implemente a busca aqui e adicione
    # as manchetes à lista `all_headlines`.
    # ... (Seu código para buscar outras fontes, se houver) ...


    # Adiciona uma mensagem padrão caso nenhuma manchete tenha sido carregada com sucesso
    if not all_headlines or all(msg.startswith("CNN Brasil: Erro") for msg in all_headlines):
         all_headlines = ["Erro ao carregar notícias da CNN Brasil ou fontes indisponíveis."]
         print("DEBUG Flask: Nenhuma manchete válida da CNN Brasil coletada, retornando mensagem de erro/fallback.")


    # Retorna as manchetes em formato JSON
    return jsonify({"headlines": all_headlines})
# --- FIM DA ROTA AJUSTADA ---

# --- Rota da API para Informações Operacionais (Letreiro Inferior) ---
# --- Rota da API para Informações Operacionais (Letreiro Inferior) ---
@app.route('/api/operational_info')
def get_operational_info():
    # Estas são as informações que você quer exibir em sequência.
    # Cada item da lista será uma "informação" no letreiro.
    operational_texts = [
        "HUB Muriaé Informa: Rotas No-Show já estão liberadas para carregamento imediato! Procure o Analista de Transporte para mais orientações. | Carregamento Mercadão! As rotas liberadas para Carregamento já estão disponíveis, dirija-se até sua Estação.",
        "Atenção motoristas: Verifiquem documentação antes de se dirigir aos pátios de carregamento. | Prioridade de carregamento para veículos com agendamento prévio. Mantenha-se informado via rádio.",
        "Atenção: Nova Rota disponível. Várias cidades para atendimento . | HUB Muriaé: Todos os motoristas devem realizar o check-in na entrada.",
        "Atenção logística: Motorista só movimente o veículo após a liberação. | Informamos: Acompanhe seu carregamento através da página de Status de Carregamento.",
        "Segurança em primeiro lugar: Use sempre EPIs nas áreas de carregamento. | HUB Muriaé Informa: Acompanhe a Fila de Carregamento pela TV ou diretamente em seu celular." |
        "HUB Muriaé: Verifique o quadro de avisos para informações importantes. | Atenção motoristas: Utilize sempre os equipamentos de segurança."  |
        "Atenção motoristas: Utilize sempre os equipamentos de segurança. | Comunique-se com a equipe para otimizar seu carregamento."  |
        "Previsão do tempo: Fique atento às condições climáticas."
    ]
    
    # Retornamos a lista completa de informações.
    # O random.choice foi removido, pois queremos todas as informações.
    return jsonify({"info": operational_texts})



# -------- FIM DA ROTA PAINEL --------




# ------ Registros Finalizados ------

@app.route('/registros_finalizados', methods=['GET'])
def registros_finalizados():
    # Parâmetro para selecionar o banco de dados
    db_name = request.args.get('db_name', 'all') # Padrão: 'all' para exibir ambos

    data_filtro_str = request.args.get('data', '')
    tipo_entrega_filtro = request.args.get('tipo_entrega', '')
    rota_filtro = request.args.get('rota', '')
    finalizado_filtro_str = request.args.get('finalizado', '')
    
    pagina = request.args.get('pagina', 1, type=int)
    per_page = REGISTROS_POR_PAGINA

    registros_items = []
    no_show_items = []
    display_db_name = "Todos os Registros" # Padrão

    # Condicionalmente consulta a tabela 'registros' (Modelo Registro)
    if db_name == 'registros' or db_name == 'all':
        query_registros = Registro.query

        if data_filtro_str:
            try:
                data_filtro_dt = datetime.strptime(data_filtro_str, '%Y-%m-%d').date()
                query_registros = query_registros.filter(db.func.date(Registro.data_hora_login) == data_filtro_dt)
            except ValueError:
                pass

        if tipo_entrega_filtro:
            query_registros = query_registros.filter(Registro.tipo_entrega.ilike(f'%{tipo_entrega_filtro}%'))

        if rota_filtro:
            query_registros = query_registros.filter(Registro.rota.ilike(f'%{rota_filtro}%'))

        if finalizado_filtro_str != '':
            finalizado_int = int(finalizado_filtro_str)
            query_registros = query_registros.filter(Registro.finalizada == finalizado_int)
        
        registros_items = query_registros.all()

    # Condicionalmente consulta a tabela 'no_show' (Modelo NoShow)
    if db_name == 'no_show' or db_name == 'all':
        query_no_show = NoShow.query

        if data_filtro_str:
            try:
                data_filtro_dt = datetime.strptime(data_filtro_str, '%Y-%m-%d').date()
                query_no_show = query_no_show.filter(db.func.date(NoShow.data_hora_login) == data_filtro_dt)
            except ValueError:
                pass

        if tipo_entrega_filtro:
            query_no_show = query_no_show.filter(NoShow.tipo_entrega.ilike(f'%{tipo_entrega_filtro}%'))

        if rota_filtro:
            # Para NoShow, a coluna de rota é 'gaiola'
            query_no_show = query_no_show.filter(NoShow.gaiola.ilike(f'%{rota_filtro}%'))

        if finalizado_filtro_str != '':
            finalizado_int = int(finalizado_filtro_str)
            query_no_show = query_no_show.filter(NoShow.finalizada == finalizado_int)

        no_show_items = query_no_show.all()

    # --- Combina ou seleciona os resultados com base em db_name ---
    if db_name == 'registros':
        all_records = registros_items
        display_db_name = "Registros Principais"
    elif db_name == 'no_show':
        all_records = no_show_items
        display_db_name = "Registros de No-Show"
    else: # 'all' ou qualquer outro valor
        all_records = registros_items + no_show_items
        display_db_name = "Todos os Registros"


    # --- Ordena os resultados ---
    all_records = sorted(all_records, key=lambda x: x.data_hora_login, reverse=True)

    # --- Paginação manual da lista combinada ---
    total_registros = len(all_records)
    total_paginas = ceil(total_registros / per_page) if total_registros > 0 else 1
    
    start_index = (pagina - 1) * per_page
    end_index = start_index + per_page
    paginated_records = all_records[start_index:end_index]

    return render_template('registros_finalizados.html',
                           registros=paginated_records, # Passa a lista combinada e paginada
                           total_paginas=total_paginas,
                           pagina=pagina,
                           data=data_filtro_str,
                           tipo_entrega=tipo_entrega_filtro,
                           rota=rota_filtro,
                           finalizado=finalizado_filtro_str,
                           db_name=db_name, # Passa o nome do DB selecionado para o template
                           display_db_name=display_db_name) # Nome amigável para exibição



# ... o restante do seu app.py ...
# (Todas as suas outras rotas aqui: /sucesso, /boas_vindas, /todos_registros, /registros, /historico, /associacao, etc.)


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)