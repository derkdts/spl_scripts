1)После установки и инициализации каждой из нод неодходимо зайти в одну из нод и обьявить его капитаном
`sudo /opt/splunk/bin/splunk bootstrap shcluster-captain`
2) Добавление нод `sudo /opt/splunk/bin/splunk add shcluster-member -new_member_uri https://splunk-sh1:8089 -auth admin:adminadmin`
