sudo pip3 install -r requirements.txt
sudo cp heart.ini /etc/uwsgi/apps/
sudo cp agents_heart.conf /etc/supervisor/conf.d/
sudo cp agents_heart_nginx.conf /etc/nginx/sites-enabled/
sudo supervisorctl update
sudo systemctl restart nginx
sudo certbot --nginx -d heart.medsenger.ru
