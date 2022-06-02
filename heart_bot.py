import json
import time
from threading import Thread
from flask import Flask, request, render_template
from config import *
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from medsenger_api import *
from mail_api import *

app = Flask(__name__)
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
            print("{}: Reactivate contract {}".format(gts(), contract.id))
        else:
            contract = Contracts(id=contract_id)

            if data.get('params'):
                code = data['params'].get('heart_device_code')
                if code:
                    contract.code = code

            db.session.add(contract)

            print("{}: Add contract {}".format(gts(), contract.id))

        db.session.commit()

        medsenger_api.send_message(contract_id,
                                   f"""Подключена интеграция с карманным монитором сердечного ритма "Сердечко". Чтобы отправить ЭКГ врачу, вам нужно:<br><br><ul><li>установить мобильное приложение ECG Mob (<a target="_blank" href="https://apps.apple.com/ru/app/ecg-mob/id1406511388">iOS</a> / <a target="_blank" href="https://play.google.com/store/apps/details?id=ru.bioss.ecgmob&hl=ru&gl=US">Android</a>);</li><li>снять ЭКГ, используя прибор и мобильное приложение;</li><li>отправить PDF файл с ЭКГ в приложение Medsenger через меню "поделиться" (на Android) или просто отправить файл на почту <strong>cardio+{contract_id}@medsenger.ru</strong> (на iOS и Android).</ul><br>Для удобства, адрес <strong>cardio+{contract_id}@medsenger.ru</strong> можно записать в настройках приложения ECG mob.""",
                                   only_patient=True)
        medsenger_api.add_record(contract_id, 'doctor_action',
                                 'Подключен прибор "Сердечко".')


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

            print("{}: Deactivate contract {}".format(gts(), contract.id))
        else:
            print('contract not found')

        medsenger_api.add_record(data.get('contract_id'), 'doctor_action',
                                 'Отключен прибор "Сердечко".')

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
                    cid = extract_contract_id(message)

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

                    if contract.code in subject or int(cid) == contract.id:
                        print(subject, contract.id)
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


if __name__ == "__main__":
    t = Thread(target=sender)
    t.start()

    app.run(port=PORT, host=HOST)
