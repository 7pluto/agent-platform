{{- define "agent-platform.name" -}}agent-platform{{- end -}}
{{- define "agent-platform.labels" -}}
app.kubernetes.io/name: {{ include "agent-platform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}