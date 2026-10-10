# Case example-stuck-loading: next step

**Decision:** Request information

No explanation is clearly ahead (h_proxy_websocket, h_subpath, h_cors_xsrf, unlisted_cause remain plausible). The steps below are the ones whose answers best separate them per unit of user effort.

## Next steps

1. **[question]** Is the app served through a reverse proxy or load balancer (for example nginx, Apache, Traefik or a cloud load balancer)?
   - facet `reverse_proxy`, gain 0.102 bits, cost 1
   - why: 'yes' favours h_proxy_websocket; 'no' favours h_subpath, h_cors_xsrf, h_broken_env, an unlisted cause
2. **[question]** Is the app opened under a URL sub-path (e.g. https://example.com/myapp/) rather than at the root of the domain?
   - facet `served_under_subpath`, gain 0.069 bits, cost 1
   - why: 'yes' favours h_subpath; 'no' favours h_proxy_websocket, h_cors_xsrf, h_broken_env, an unlisted cause

## Known facts

| facet | value | source | quote |
|---|---|---|---|
| deployment_target | remote_server | title | App stays on the loading screen when deployed on our server |
| reproduces_locally | no | body | The app opens on my own machine, but on the server it stays on the loading screen ("Please wait...") forever. |
| reinstall_resolves | no | body | Reinstalling did not help. |

## Hypotheses

| id | prior | posterior | evidence | conflicts | statement |
|---|---|---|---|---|---|
| h_proxy_websocket | 0.36 | 0.44 | strong | - | A reverse proxy in front of the server does not forward WebSocket upgrade headers, so the frontend never connects to /_stcore/stream. |
| h_subpath | 0.18 | 0.22 | strong | - | The app is served under a sub-path without setting server.baseUrlPath, so frontend requests go to the wrong URL. |
| h_cors_xsrf | 0.15 | 0.18 | strong | - | CORS/XSRF protection rejects the browser connection because the public origin differs from the server address. |
| unlisted_cause | 0.20 | 0.14 | none | - | A cause that none of the retrieved evidence describes. |
| h_broken_env | 0.11 | 0.02 | weak | reinstall_resolves=no | The server's Python environment is broken (dependency conflict), so the app never finishes starting. |

## Still unknown

- `reverse_proxy`: Whether a reverse proxy / load balancer sits in front of the app (relevant to h_proxy_websocket; gain 0.102)
- `websocket_error_in_console`: Whether the browser reports a failed WebSocket connection (relevant to h_proxy_websocket, h_cors_xsrf; gain 0.102)
- `health_endpoint_ok`: Whether the Streamlit server answers its health endpoint (relevant to h_proxy_websocket, h_subpath, h_cors_xsrf, h_broken_env; gain 0.087)
- `served_under_subpath`: Whether the app is served under a URL sub-path (relevant to h_subpath; gain 0.069)

## Not asked again

- `reproduces_locally`: already stated (body: "The app opens on my own machine, but on the server it stays on the loading screen ("Please wait...") forever.") -> reproduces_locally=no
- `reinstall_resolves`: already performed (body: "Reinstalling did not help.") -> reinstall_resolves=no

## Limitations

- h_broken_env conflicts with reported facts: reinstall_resolves=no.
