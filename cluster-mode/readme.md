## Инфраструктура Splunk Enterprise (SHCluster + Indexer Cluster) в Docker
Данный репозиторий содержит конфигурацию для развертывания отказоустойчивой локальной среды Splunk с использованием Docker Compose и балансировщика NGINX.
## Архитектура стека:

* Балансировщик (splunk-lb): NGINX, распределяет сессии пользователей между Search Head.
* Деплоер (splunk-deployer): Совмещает роли Deployer (управление SHC) и Cluster Manager (управление индексаторами).
* Search Head Cluster (splunk-sh1, sh2, sh3): Кластер поисковых нод (кворум Raft).
* Indexer Cluster (splunk-idx1, idx2): Кластер нод хранения и индексации данных.

------------------------------
## 1. Запуск контейнеров
Выполните команду для старта:
```
docker compose up -d
```

docker logs -f splunk-sh1

Переходите к следующему шагу только тогда, когда в логах появится строка:
> Ansible playbook complete, Splunk is ready for use!
------------------------------
## 🛠️ Пошаговая инициализация кластеров (Выполняется один раз)
После того как контейнеры успешно поднялись, их необходимо связать в единую сеть консенсуса. Выполните следующие шаги в терминале:
## Шаг 1. Настройка кластера Индексаторов (idx)
Включаем роль хранения данных (peer) на индексаторах и задаем порт репликации логов:

# Настройка первой ноды хранения
```
docker exec -it splunk-idx1 sudo /opt/splunk/bin/splunk edit cluster-config  -auth admin:adminadmin   -mode peer  -master_uri https://splunk-deployer:8089   -replication_port 8080   -secret my_indexer_cluster_secret
```

# Настройка второй ноды хранения
```
docker exec -it splunk-idx2 sudo /opt/splunk/bin/splunk edit cluster-config   -auth admin:adminadmin   -mode peer   -master_uri https://splunk-deployer:8089   -replication_port 8080   -secret my_indexer_cluster_secret
```

# Перезапуск процессов для применения роли
```
docker exec -it splunk-idx1 sudo /opt/splunk/bin/splunk restart
docker exec -it splunk-idx2 sudo /opt/splunk/bin/splunk restart
```
## Шаг 2. Включение Raft-интерфейсов на Search Head нодах (sh)
Активируем встроенный движок кластеризации на поисковых головах и выделяем порт репликации артефактов (8100):

```
docker exec -it splunk-sh1 sudo /opt/splunk/bin/splunk init shcluster-config -auth admin:adminadmin -mgmt_uri https://splunk-sh1:8089 -replication_port 8100 -replication_factor 3 -secret my_shc_secret_phrase -conf_deploy_fetch_url https://splunk-deployer:8089
docker exec -it splunk-sh2 sudo /opt/splunk/bin/splunk init shcluster-config -auth admin:adminadmin -mgmt_uri https://splunk-sh2:8089 -replication_port 8100 -replication_factor 3 -secret my_shc_secret_phrase -conf_deploy_fetch_url https://splunk-deployer:8089
docker exec -it splunk-sh3 sudo /opt/splunk/bin/splunk init shcluster-config -auth admin:adminadmin -mgmt_uri https://splunk-sh3:8089 -replication_port 8100 -replication_factor 3 -secret my_shc_secret_phrase -conf_deploy_fetch_url https://splunk-deployer:8089
```
# Перезапуск процессов для открытия портов
```
docker exec -it splunk-sh1 sudo /opt/splunk/bin/splunk restart
docker exec -it splunk-sh2 sudo /opt/splunk/bin/splunk restart
docker exec -it splunk-sh3 sudo /opt/splunk/bin/splunk restart
```

Подождите 30 секунд, пока процессы перезапустятся.
## Шаг 3. Запуск Bootstrap и сборка SH-кластера
Выбираем первый Search Head (splunk-sh1) в качестве капитана:

```
docker exec -it splunk-sh1 sudo /opt/splunk/bin/splunk bootstrap shcluster-captain   -servers_list "https://splunk-sh1:8089,https://splunk-sh2:8089,https://splunk-sh3:8089"   -auth admin:adminadmin
```

Если ноды sh2 и sh3 не появились в статусе автоматически в течение минуты, принудительно добавьте их к капитану:
```
docker exec -it splunk-sh2 sudo /opt/splunk/bin/splunk add shcluster-member -current_member_uri https://splunk-sh1:8089 -auth admin:adminadmin
docker exec -it splunk-sh3 sudo /opt/splunk/bin/splunk add shcluster-member -current_member_uri https://splunk-sh1:8089 -auth admin:adminadmin
```
------------------------------
## 🔗 Доступ к веб-интерфейсам (UI)

* Интерфейс пользователя / Поиск (Search Head Cluster):
👉 http://splunk_cluster.localhost (Трафик идет через балансировщик NGINX, сессии привязываются по ip_hash).
* Интерфейс администратора (Deployer / Cluster Manager):
👉 http://127.0.0.2:8000 (Прямое подключение в обход балансировщика для мониторинга состояния нод idx).

Данные для авторизации по умолчанию:

> * Логин: admin
> * Пароль: adminadmin

------------------------------
## 📊 Проверка статуса (Здоровье кластера)
Чтобы убедиться, что все компоненты видят друг друга и данные реплицируются:

   1. Проверка Search Head кластера (выполнять на splunk-sh1):
   
   ```
   docker exec -it splunk-sh1 sudo /opt/splunk/bin/splunk show shcluster-status -auth admin:adminadmin
   ```
   
   Ожидаемый статус: Stable, в списке участников (Members) должны быть три ноды с именами контейнеров.
   2. Проверка Индексаторов (выполнять строго на splunk-deployer):
   
   ```
   docker exec -it splunk-deployer sudo /opt/splunk/bin/splunk list cluster-peers -auth admin:adminadmin
   ```
   
   Ожидаемый статус: Обе ноды splunk-idx1 и splunk-idx2 должны иметь статус Up.

------------------------------


## Результаты
<img width="1449" height="511" alt="image" src="https://github.com/user-attachments/assets/96dfe3ac-8239-47f5-93eb-05a6218767ab" />
