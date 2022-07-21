import json
import time
from threading import Thread
from flask import Flask, request, render_template, abort, jsonify
from config import *
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from medsenger_api import *
from mail_api import *

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1000 * 1000
db_string = "postgresql://{}:{}@{}:{}/{}".format(DB_LOGIN, DB_PASSWORD, DB_HOST, DB_PORT, DB_DATABASE)
app.config['SQLALCHEMY_DATABASE_URI'] = db_string
db = SQLAlchemy(app)

medsenger_api = AgentApiClient(APP_KEY, MAIN_HOST, debug=True)


class Params(db.Model):
    name = db.Column(db.String, primary_key=True)
    value = db.Column(db.String, nullable=True)


class Contracts(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    active = db.Column(db.Boolean, default=True)
    code = db.Column(db.String, nullable=True)
    email = db.Column(db.String, nullable=True)


try:
    db.create_all()

    query = Params.query.filter_by(name='last_id')
    if query.count() == 0:
        param = Params(name='last_id', value='-1')
        db.session.add(param)
        db.session.commit()

except:
    print('cant create structure')


def gts():
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")


@app.route('/status', methods=['POST'])
def status():
    data = request.json

    if data['api_key'] != APP_KEY:
        return 'invalid key'

    contract_ids = [l[0] for l in db.session.query(Contracts.id).filter_by(active=True).all()]

    answer = {
        "is_tracking_data": True,
        "supported_scenarios": ['heartfailure', 'stenocardia', 'fibrillation'],
        "tracked_contracts": contract_ids
    }

    return json.dumps(answer)


@app.route('/init', methods=['POST'])
def init():
    data = request.json

    if data['api_key'] != APP_KEY:
        return 'invalid key'

    try:
        contract_id = int(data['contract_id'])
        query = Contracts.query.filter_by(id=contract_id)
        if query.count() != 0:
            contract = query.first()
            contract.active = True

            if data.get('params'):
                code = data['params'].get('heart_device_code')
                email = data['params'].get('heart_device_email')
            else:
                code = None
                email = None

            if code:
                contract.code = code

            if email:
                contract.email = email
            else:
                contract.email = f'cardio+{contract_id}@medsenger.ru'

            print("{}: Reactivate contract {}".format(gts(), contract.id))
        else:
            contract = Contracts(id=contract_id)

            if data.get('params'):
                code = data['params'].get('heart_device_code')
                email = data['params'].get('heart_device_email')
            else:
                code = None
                email = None
            if code:
                contract.code = code

            if email:
                contract.email = email
            else:
                contract.email = f'cardio+{contract_id}@medsenger.ru'

            db.session.add(contract)

            print("{}: Add contract {}".format(gts(), contract.id))

        db.session.commit()

        medsenger_api.send_message(contract_id,
                                   f"""Подключена интеграция с карманным монитором сердечного ритма "Сердечко". Чтобы отправить ЭКГ врачу, вам нужно:<br><br><ul><li>установить мобильное приложение ECG Mob (<a target="_blank" href="https://apps.apple.com/ru/app/ecg-mob/id1406511388">iOS</a> / <a target="_blank" href="https://play.google.com/store/apps/details?id=ru.bioss.ecgmob&hl=ru&gl=US">Android</a>);</li><li>снять ЭКГ, используя прибор и мобильное приложение;</li><li>отправить PDF файл с ЭКГ в приложение Medsenger через меню "поделиться" (на Android) или просто отправить файл на почту <strong>{contract.email}</strong> (на iOS и Android).</ul><br>Для удобства, адрес <strong>{contract.email}</strong> можно записать в настройках приложения ECG mob.""",
                                   only_patient=True)
        medsenger_api.add_record(contract_id, 'doctor_action',
                                 f'Подключен прибор "Сердечко" {contract.code} / {contract.email}.')


    except Exception as e:
        print(e)
        return "error"
    return 'ok'


@app.route('/remove', methods=['POST'])
def remove():
    data = request.json

    if data['api_key'] != APP_KEY:
        print('invalid key')
        return 'invalid key'

    try:
        contract_id = str(data['contract_id'])
        query = Contracts.query.filter_by(id=contract_id)

        if query.count() != 0:
            contract = query.first()
            contract.active = False
            db.session.commit()

            medsenger_api.add_record(data.get('contract_id'), 'doctor_action',
                                     f'Отключен прибор "Сердечко" ({contract.code} / {contract.email}).')

            print("{}: Deactivate contract {}".format(gts(), contract.id))
        else:
            print('contract not found')



    except Exception as e:
        print(e)
        return "error"

    return 'ok'


@app.route('/settings', methods=['GET'])
def settings():
    key = request.args.get('api_key', '')

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    try:
        contract_id = int(request.args.get('contract_id'))
        query = Contracts.query.filter_by(id=contract_id)
        if query.count() != 0:
            contract = query.first()
        else:
            return "<strong>Ошибка. Контракт не найден.</strong> Попробуйте отключить и снова подключить интеллектуальный агент к каналу консультирвоания. Если это не сработает, свяжитесь с технической поддержкой."

    except Exception as e:
        print(e)
        return "error"

    return render_template('settings.html', contract=contract)


@app.route('/settings', methods=['POST'])
def setting_save():
    key = request.args.get('api_key', '')

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    try:
        contract_id = int(request.args.get('contract_id'))
        query = Contracts.query.filter_by(id=contract_id)
        if query.count() != 0:
            contract = query.first()
            contract.code = request.form.get('code')
            contract.email = request.form.get('email')
            db.session.commit()
        else:
            return "<strong>Ошибка. Контракт не найден.</strong> Попробуйте отключить и снова подключить интеллектуальный агент к каналу консультирвоания. Если это не сработает, свяжитесь с технической поддержкой."

    except Exception as e:
        print(e)
        return "error"

    return """
        <strong>Спасибо, окно можно закрыть</strong><script>window.parent.postMessage('close-modal-success','*');</script>
        """


@app.route('/', methods=['GET'])
def index():
    return 'waiting for the thunder!'


def tasks():
    try:
        contracts = Contracts.query.filter_by(active=True).all()
        param = Params.query.filter_by(name='last_id').first()

        last_id, messages = get_messages(param.value)

        if last_id:
            param.value = last_id
            db.session.commit()

            for contract in contracts:
                if not contract.code:
                    continue
                for message in messages:

                    hds = decode_header(message['subject'])
                    sender, cid = extract_contract_id(message)

                    if not hds and not cid:
                        continue

                    if hds:
                        data, encoding = hds[0]
                        if encoding:
                            subject = data.decode(encoding)
                        else:
                            subject = data
                    else:
                        subject = ""

                    if contract.code in subject or int(cid) == contract.id or sender == contract.email:
                        attachments = get_attachments(message)
                        medsenger_api.send_message(contract.id, text="результаты снятия ЭКГ", attachments=attachments, send_from='patient')

                        medsenger_api.send_message(contract.id,
                                                   'Вы прислали ЭКГ. Пожалуйста, напишите врачу, почему Вы решили снять ЭКГ и какие ощущения Вы испытываете?',
                                                   only_patient=True)
    except Exception as e:
        print(e)


def sender():
    while True:
        tasks()
        time.sleep(60)


@app.route('/message', methods=['POST'])
def save_message():
    data = request.json
    key = data['api_key']

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    if data.get('message', {}).get('attachments'):
        for attachment in data['message']['attachments']:
            if 'ecg_' in attachment['name']:
                medsenger_api.send_message(data['contract_id'],
                                           'Похоже, что Вы прислали ЭКГ. Пожалуйста, напишите врачу, почему Вы решили снять ЭКГ и какие ощущения Вы испытываете?',
                                           only_patient=True)

    return "ok"


@app.route('/api/receive', methods=['POST'])
def receive_ecg():
    contract_id = request.form.get('contract_id')

    if not contract_id:
        abort(422, "No contract_id")

    agent_token = request.form.get('agent_token')

    if not agent_token:
        abort(422, "No agent_token")

    answer = medsenger_api.get_agent_token(contract_id)

    if not answer or answer.get('agent_token') != agent_token:
        abort(422, "Incorrect token")

    if 'ecg' in request.files:
        file = request.files['ecg']
        filename = file.filename
        data = file.read()

        if not filename or not data:
            abort(422, "No filename")
        else:
            medsenger_api.send_message(contract_id, "Результаты снятия ЭКГ c Сердечка.", send_from='patient', need_answer=True, attachments=[prepare_binary(filename, data)])
            return 'ok'

    else:
        abort(422, "No file")


@app.route('/api/receive', methods=['GET'])
def receive_ecg_test():
    return """
    <form method="POST" enctype="multipart/form-data">
        contract_id <input name="contract_id"><br>
        agent_token <input name="agent_token"><br>
        ecg <input name="ecg" type="file"><br>
        <button>go</button>
    </form>
    """


@app.route('/.well-known/apple-app-site-association')
def apple_deeplink():
    return jsonify({
        "applinks": {
            "apps": [],
            "details": [
                {
                    "appID": "TR6RHMAD2G.ru.bioss.cardio",
                    "paths": [
                        "*"
                    ]
                }
            ]
        }
    }
    )

@app.route('/.well-known/assetlinks.json')
def android_deeplink():
    return jsonify([{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app", "package_name": "ru.bioss.ecgmob",
            "sha256_cert_fingerprints": ["4F:56:2B:08:4C:6A:95:E9:4E:DA:96:B8:BA:8A:B5:EF:D5:3A:4C:6D:8D:B8:5E:DD:8F:76:AE:2A:B5:97:C1:E7"],
        },
    }])


if __name__ == "__main__":
    t = Thread(target=sender)
    t.start()

    app.run(port=PORT, host=HOST)
