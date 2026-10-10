# Case example-stuck-loading-turn3: next step

**Decision:** Propose an answer (h_proxy_websocket)

h_proxy_websocket is the leading explanation (posterior 0.65, runner-up 0.15) and is backed by authoritative sources. Any step listed is an optional confirmation.

## Next steps

_None._

## Known facts

| facet | value | source | quote |
|---|---|---|---|
| deployment_target | remote_server | title | App stays on the loading screen when deployed on our server |
| reproduces_locally | no | body | The app opens on my own machine, but on the server it stays on the loading screen ("Please wait...") forever. |
| reinstall_resolves | no | body | Reinstalling did not help. |
| reverse_proxy | yes | comment:c2 | Yes, nginx is in front of it. |
| websocket_error_in_console | yes | comment:c3 | The console says: WebSocket connection to wss://apps.example.com/_stcore/stream failed. |
| error_message | WebSocket connection to wss://apps.example.com/_stcore/stream failed. | comment:c3 | The console says: WebSocket connection to wss://apps.example.com/_stcore/stream failed. |

## Hypotheses

| id | prior | posterior | evidence | conflicts | statement |
|---|---|---|---|---|---|
| h_proxy_websocket | 0.36 | 0.65 | strong | - | A reverse proxy in front of the server does not forward WebSocket upgrade headers, so the frontend never connects to /_stcore/stream. |
| h_cors_xsrf | 0.15 | 0.15 | strong | - | CORS/XSRF protection rejects the browser connection because the public origin differs from the server address. |
| h_subpath | 0.18 | 0.11 | strong | - | The app is served under a sub-path without setting server.baseUrlPath, so frontend requests go to the wrong URL. |
| unlisted_cause | 0.20 | 0.07 | none | - | A cause that none of the retrieved evidence describes. |
| h_broken_env | 0.11 | 0.01 | weak | reinstall_resolves=no | The server's Python environment is broken (dependency conflict), so the app never finishes starting. |

## Still unknown

- `health_endpoint_ok`: Whether the Streamlit server answers its health endpoint (relevant to h_proxy_websocket, h_subpath, h_cors_xsrf, h_broken_env; gain 0.050)
- `served_under_subpath`: Whether the app is served under a URL sub-path (relevant to h_subpath; gain 0.039)

## Not asked again

- `reverse_proxy`: already stated (comment:c2: "Yes, nginx is in front of it.") -> reverse_proxy=yes
- `reproduces_locally`: already stated (body: "The app opens on my own machine, but on the server it stays on the loading screen ("Please wait...") forever.") -> reproduces_locally=no
- `websocket_error_in_console`: already performed (comment:c3: "The console says: WebSocket connection to wss://apps.example.com/_stcore/stream failed.") -> websocket_error_in_console=yes
- `reinstall_resolves`: already performed (body: "Reinstalling did not help.") -> reinstall_resolves=no

## Limitations

- h_broken_env conflicts with reported facts: reinstall_resolves=no.
