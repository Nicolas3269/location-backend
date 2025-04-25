# location-backend

apt-get install libspatialite-dev spatialite-bin
sudo apt-get install libsqlite3-mod-spatialite python3-gdal gdal-bin

# Carefull for rent_control

python manage.py makemigrations rent_control
python manage.py migrate rent_control --database=geodb

# map

http://localhost:8003/admin/rent_control/rentcontrolarea/region_map/

# docker:

docker build -t hestia-backend .
docker run -p 8003:8000 --env-file .env hestia-backend
