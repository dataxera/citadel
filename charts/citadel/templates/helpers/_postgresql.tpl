{{/*
Citadel database environment variables
*/}}
{{- define "citadel.dbEnv" -}}
{{- if .Values.postgresql.enabled }}
- name: CITADEL_DB_HOST
  valueFrom:
    secretKeyRef:
      name: {{ include "citadel.fullname" . }}-db-app
      key: host
- name: CITADEL_DB_PORT
  valueFrom:
    secretKeyRef:
      name: {{ include "citadel.fullname" . }}-db-app
      key: port
- name: CITADEL_DB_NAME
  valueFrom:
    secretKeyRef:
      name: {{ include "citadel.fullname" . }}-db-app
      key: dbname
- name: CITADEL_DB_USER
  valueFrom:
    secretKeyRef:
      name: {{ include "citadel.fullname" . }}-db-app
      key: user
- name: CITADEL_DB_PASS
  valueFrom:
    secretKeyRef:
      name: {{ include "citadel.fullname" . }}-db-app
      key: password
{{- end }}
{{- end }}
