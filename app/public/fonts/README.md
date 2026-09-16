# Self-hosted IBM Plex fonts

Self-hosted to let the app's Content-Security-Policy drop fonts.googleapis.com /
fonts.gstatic.com. Downloaded 2026-09-16.

- `ibm-plex-sans-400.woff2` -- IBM Plex Sans Regular (400), latin subset, v23
- `ibm-plex-sans-500.woff2` -- IBM Plex Sans Medium (500), latin subset, v23
- `ibm-plex-sans-600.woff2` -- IBM Plex Sans SemiBold (600), latin subset, v23
- `ibm-plex-sans-700.woff2` -- IBM Plex Sans Bold (700), latin subset, v23
- `ibm-plex-mono-400.woff2` -- IBM Plex Mono Regular (400), latin subset, v20
- `ibm-plex-mono-600.woff2` -- IBM Plex Mono SemiBold (600), latin subset, v20

All six were fetched from Google Fonts' `fonts.gstatic.com` CDN via the
`css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;600`
endpoint (same family/weights the app previously loaded live), taking only the
`/* latin */` `@font-face` block per weight. `OFL.txt` is the unmodified
SIL Open Font License 1.1 text from https://github.com/IBM/plex/blob/master/LICENSE.txt.

IBM Plex is licensed under the SIL Open Font License 1.1 -- see `OFL.txt`.
