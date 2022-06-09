from heart_bot import *
from apscheduler.schedulers.background import BlockingScheduler


scheduler = BlockingScheduler()
scheduler.add_job(tasks, 'interval', minutes=1)
scheduler.start()