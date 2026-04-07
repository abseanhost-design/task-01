import json
import uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

DATA_FILE = Path('data.json')
LEGACY_WALLET_FILE = Path('wallet_data.json')

DEFAULT_STATE = {
    'wallet': {
        'balance': 1442.80,
        'bankLinked': False,
        'history': []
    },
    'users': [],
    'teams': [
        {
            'teamId': '70003',
            'name': 'Starter Team',
            'description': 'Default starter team for new users'
        }
    ],
    'tasks': [
        {'taskId': 'whatsapp', 'name': 'WhatsApp task', 'reward': 80, 'description': 'Share the update over WhatsApp'},
        {'taskId': 'youtube', 'name': 'YouTube task', 'reward': 35, 'description': 'Watch a short tutorial video'},
        {'taskId': 'facebook', 'name': 'Facebook task', 'reward': 30, 'description': 'Post project progress on Facebook'},
        {'taskId': 'line', 'name': 'Line task', 'reward': 25, 'description': 'Share the task link on Line'},
        {'taskId': 'x', 'name': 'X task', 'reward': 40, 'description': 'Share the task update on X'}
    ],
    'withdrawals': []
}


def initialize_data_file():
    if DATA_FILE.exists():
        return

    if LEGACY_WALLET_FILE.exists():
        legacy = json.loads(LEGACY_WALLET_FILE.read_text(encoding='utf-8'))
        state = DEFAULT_STATE.copy()
        state['wallet'].update({
            'balance': float(legacy.get('balance', state['wallet']['balance'])),
            'bankLinked': bool(legacy.get('bankLinked', state['wallet']['bankLinked'])),
            'history': legacy.get('history', state['wallet']['history']) or []
        })
        DATA_FILE.write_text(json.dumps(state, indent=2), encoding='utf-8')
    else:
        DATA_FILE.write_text(json.dumps(DEFAULT_STATE, indent=2), encoding='utf-8')


def read_state():
    return json.loads(DATA_FILE.read_text(encoding='utf-8'))


def write_state(state):
    DATA_FILE.write_text(json.dumps(state, indent=2), encoding='utf-8')


def generate_user_id():
    return f"T01-{uuid.uuid4().hex[:8].upper()}"


def generate_referral_code():
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    return 'REF-' + ''.join(uuid.uuid4().hex.upper()[i] for i in range(6))


def get_auth_token():
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header.split(' ', 1)[1].strip()
    return None


def get_user_by_token(state, token):
    return next((user for user in state['users'] if user.get('token') == token), None)


def get_user_by_phone(state, phone):
    return next((user for user in state['users'] if user.get('phone') == phone), None)


def user_safe(user):
    if not user:
        return None
    return {
        'userId': user['userId'],
        'phone': user['phone'],
        'name': user['name'],
        'teamId': user['teamId'],
        'points': user.get('points', 0),
        'completedTasks': user.get('completedTasks', 0),
        'balance': user.get('balance', 0),
        'referralCode': user.get('referralCode'),
        'referredBy': user.get('referredBy')
    }


def require_auth():
    token = get_auth_token()
    if not token:
        return None
    state = read_state()
    return get_user_by_token(state, token)


@app.route('/', methods=['GET'])
def serve_index():
    return app.send_static_file('index.html')


@app.route('/signup', methods=['GET'])
def serve_signup():
    return app.send_static_file('signup.html')


@app.route('/login', methods=['GET'])
def serve_login():
    return app.send_static_file('login.html')


@app.route('/tasks', methods=['GET'])
def serve_tasks():
    return app.send_static_file('tasks.html')


@app.route('/team', methods=['GET'])
def serve_team():
    return app.send_static_file('team.html')


@app.route('/api/signup', methods=['POST'])
def api_signup():
    payload = request.get_json(force=True)
    phone = str(payload.get('phone', '')).strip()
    password = payload.get('password', '').strip()
    name = payload.get('name', '').strip()
    team_id = payload.get('teamId', '70003').strip() or '70003'
    referral_code = payload.get('referralCode', '').strip()

    if not phone or not password or not name:
        return jsonify(error='missing_fields', message='Phone, name, and password are required'), 400
    if len(phone) < 10 or not phone.isdigit():
        return jsonify(error='invalid_phone', message='Phone number must be numeric and at least 10 digits'), 400

    state = read_state()
    if get_user_by_phone(state, phone):
        return jsonify(error='user_exists', message='Phone number is already registered'), 400

    team = next((team for team in state['teams'] if team['teamId'] == team_id), None)
    if not team:
        team = {'teamId': team_id, 'name': f'Team {team_id}', 'description': 'Created via signup'}
        state['teams'].append(team)

    token = uuid.uuid4().hex
    user = {
        'userId': generate_user_id(),
        'phone': phone,
        'name': name,
        'teamId': team_id,
        'passwordHash': generate_password_hash(password),
        'token': token,
        'referralCode': generate_referral_code(),
        'referredBy': None,
        'points': 0,
        'completedTasks': 0,
        'balance': 650.0,
        'taskHistory': []
    }

    if referral_code:
        referrer = next((user for user in state['users'] if user.get('referralCode') == referral_code), None)
        if referrer:
            user['referredBy'] = referrer['phone']
            referrer['balance'] = referrer.get('balance', 0) + 100

    state['users'].append(user)
    write_state(state)

    return jsonify(token=token, user=user_safe(user), team=team)


@app.route('/api/login', methods=['POST'])
def api_login():
    payload = request.get_json(force=True)
    phone = str(payload.get('phone', '')).strip()
    password = payload.get('password', '').strip()

    if not phone or not password:
        return jsonify(error='missing_fields', message='Phone and password are required'), 400

    state = read_state()
    user = get_user_by_phone(state, phone)
    if not user or not check_password_hash(user['passwordHash'], password):
        return jsonify(error='invalid_credentials', message='Phone or password is incorrect'), 401

    user['token'] = uuid.uuid4().hex
    write_state(state)

    return jsonify(token=user['token'], user=user_safe(user))


@app.route('/api/user', methods=['GET'])
def api_user():
    token = get_auth_token()
    if not token:
        return jsonify(error='unauthorized', message='Authorization token is required'), 401

    state = read_state()
    user = get_user_by_token(state, token)
    if not user:
        return jsonify(error='unauthorized', message='Invalid token'), 401

    team = next((team for team in state['teams'] if team['teamId'] == user['teamId']), None)
    members = [user_safe(member) for member in state['users'] if member['teamId'] == user['teamId']]

    return jsonify(user=user_safe(user), team=team, members=members)


@app.route('/api/team/<team_id>', methods=['GET'])
def api_team(team_id):
    token = get_auth_token()
    if not token:
        return jsonify(error='unauthorized', message='Authorization token is required'), 401

    state = read_state()
    user = get_user_by_token(state, token)
    if not user:
        return jsonify(error='unauthorized', message='Invalid token'), 401

    team = next((team for team in state['teams'] if team['teamId'] == team_id), None)
    if not team:
        return jsonify(error='team_not_found', message='Team not found'), 404

    members = [user_safe(member) for member in state['users'] if member['teamId'] == team_id]
    total_tasks = sum(member.get('completedTasks', 0) for member in state['users'] if member['teamId'] == team_id)
    total_points = sum(member.get('points', 0) for member in state['users'] if member['teamId'] == team_id)

    return jsonify(
        team=team,
        members=members,
        stats={
            'memberCount': len(members),
            'totalTasksCompleted': total_tasks,
            'totalPoints': total_points,
            'estimatedRevenue': total_points * 1.5
        }
    )


@app.route('/api/tasks', methods=['GET'])
def api_tasks():
    state = read_state()
    return jsonify(tasks=state['tasks'])


@app.route('/api/tasks/complete', methods=['POST'])
def api_complete_task():
    token = get_auth_token()
    if not token:
        return jsonify(error='unauthorized', message='Authorization token is required'), 401

    payload = request.get_json(force=True)
    task_id = payload.get('taskId') or payload.get('task')
    if not task_id:
        return jsonify(error='missing_fields', message='taskId is required'), 400

    state = read_state()
    user = get_user_by_token(state, token)
    if not user:
        return jsonify(error='unauthorized', message='Invalid token'), 401

    task = next((task for task in state['tasks'] if task['taskId'] == task_id), None)
    if not task:
        return jsonify(error='task_not_found', message='Task not found'), 404

    user['points'] = user.get('points', 0) + task['reward']
    user['completedTasks'] = user.get('completedTasks', 0) + 1
    user['balance'] = user.get('balance', 0) + task['reward']
    user.setdefault('taskHistory', []).append({
        'taskId': task['taskId'],
        'reward': task['reward'],
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })
    write_state(state)

    return jsonify(user=user_safe(user), task=task)


@app.route('/api/referrals', methods=['GET'])
def api_referrals():
    token = get_auth_token()
    if not token:
        return jsonify(error='unauthorized', message='Authorization token is required'), 401

    state = read_state()
    user = get_user_by_token(state, token)
    if not user:
        return jsonify(error='unauthorized', message='Invalid token'), 401

    referred_users = [user_safe(member) for member in state['users'] if member.get('referredBy') == user['phone']]
    return jsonify(
        referralCode=user.get('referralCode'),
        referralCount=len(referred_users),
        referralEarnings=len(referred_users) * 100,
        referredUsers=referred_users
    )


@app.route('/api/history', methods=['GET'])
def api_history():
    token = get_auth_token()
    if not token:
        return jsonify(error='unauthorized', message='Authorization token is required'), 401

    state = read_state()
    user = get_user_by_token(state, token)
    if not user:
        return jsonify(error='unauthorized', message='Invalid token'), 401

    user_withdrawals = [record for record in state['withdrawals'] if record.get('phone') == user['phone']]
    return jsonify(
        taskHistory=user.get('taskHistory', []),
        withdrawals=user_withdrawals,
        balance=user.get('balance', 0)
    )


@app.route('/balance', methods=['GET'])
def get_balance():
    state = read_state()
    token = get_auth_token()
    if token:
        user = get_user_by_token(state, token)
        if user:
            return jsonify(balance=user.get('balance', 0), bankLinked=state['wallet']['bankLinked'])

    return jsonify(balance=state['wallet']['balance'], bankLinked=state['wallet']['bankLinked'])


@app.route('/withdraw', methods=['POST'])
def withdraw():
    body = request.get_json(force=True)
    amount = float(body.get('amount', 0))
    state = read_state()
    token = get_auth_token()

    if amount <= 0:
        return jsonify(error='invalid_amount'), 400

    if token:
        user = get_user_by_token(state, token)
        if user:
            if amount > user.get('balance', 0):
                return jsonify(error='insufficient_balance'), 400
            user['balance'] = user.get('balance', 0) - amount
            withdrawal = {
                'phone': user['phone'],
                'amount': amount,
                'status': 'successful',
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
            state['withdrawals'].append(withdrawal)
            write_state(state)
            return jsonify(balance=user['balance'], message='success')

    if amount > state['wallet']['balance']:
        return jsonify(error='insufficient_balance'), 400

    state['wallet']['balance'] -= amount
    state['wallet']['history'].append({'type': 'withdraw', 'amount': amount, 'timestamp': datetime.utcnow().isoformat() + 'Z'})
    write_state(state)
    return jsonify(balance=state['wallet']['balance'], message='success')


@app.route('/reward', methods=['POST'])
def reward():
    body = request.get_json(force=True)
    amount = float(body.get('reward', 0))
    state = read_state()

    if amount <= 0:
        return jsonify(error='invalid_reward'), 400

    state['wallet']['balance'] += amount
    state['wallet']['history'].append({'type': 'reward', 'amount': amount, 'timestamp': datetime.utcnow().isoformat() + 'Z'})
    write_state(state)
    return jsonify(balance=state['wallet']['balance'], message='success')


@app.route('/link-bank', methods=['POST'])
def link_bank():
    state = read_state()
    state['wallet']['bankLinked'] = True
    write_state(state)
    return jsonify(bankLinked=True, message='bank_linked')


if __name__ == '__main__':
    initialize_data_file()
    app.run(debug=True, port=5000)
