1)После установки и инициализации каждой из нод неодходимо зайти в одну из нод и обьявить его капитаном
`sudo /opt/splunk/bin/splunk bootstrap shcluster-captain`
2) Добавление нод `sudo /opt/splunk/bin/splunk add shcluster-member -new_member_uri https://splunk-sh1:8089 -auth admin:adminadmin`

## Результаты
<img width="1449" height="511" alt="image" src="https://github.com/user-attachments/assets/96dfe3ac-8239-47f5-93eb-05a6218767ab" />
