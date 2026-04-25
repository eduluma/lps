{{/*
Common labels
*/}}
{{- define "lps.labels" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{/*
Image helper: resolve with fallback to global registry/tag.
Usage: {{ include "lps.image" (dict "local" .Values.api.image "global" .Values.global.image "name" "api") }}
*/}}
{{- define "lps.image" -}}
{{- $registry := .global.registry -}}
{{- $repo := default (printf "%s/%s" $registry .name) .local.repository -}}
{{- $tag := default .global.tag .local.tag -}}
{{- printf "%s:%s" $repo $tag -}}
{{- end }}

{{/*
Pull policy helper
*/}}
{{- define "lps.pullPolicy" -}}
{{- default .global.pullPolicy .local.pullPolicy -}}
{{- end }}
