# Case example-multiselect-reset-turn2: next step

**Decision:** Propose an answer (h_widget_identity)

h_widget_identity is the leading explanation (posterior 0.85, runner-up 0.09) and is backed by authoritative sources. Any step listed is an optional confirmation.

## Next steps

_None._

## Known facts

| facet | value | source | quote |
|---|---|---|---|
| streamlit_version | 1.52.0 | body | - Streamlit version: 1.52.0 |
| python_version | 3.12 | body | - Python version: 3.12 |
| browser | firefox | body | - Browser: Firefox |
| code_snippet | present | body | ```python |
| lost_after_page_reload | no | comment:c1 | No page reload, it happens on normal clicks. |
| options_change_between_reruns | yes | comment:c1 | load_items() returns a set, so the options come in a different order each time. |
| uses_callback | no | body | (not used in the code shared in this message) |
| inside_fragment | no | body | (not used in the code shared in this message) |
| inside_dialog | no | body | (not used in the code shared in this message) |
| inside_form | no | body | (not used in the code shared in this message) |
| calls_st_rerun | no | body | (not used in the code shared in this message) |
| multipage_app | no | body | (not used in the code shared in this message) |
| widget_has_key | no | body | (not used in the code shared in this message) |

## Hypotheses

| id | prior | posterior | evidence | conflicts | statement |
|---|---|---|---|---|---|
| h_widget_identity | 0.40 | 0.85 | strong | - | The multiselect has no key and its options come in a different order on each rerun, so it gets a new identity and resets. |
| unlisted_cause | 0.20 | 0.09 | none | - | A cause that none of the retrieved evidence describes. |
| h_widget_cleanup | 0.18 | 0.04 | strong | widget_has_key=no | The keyed widget is not rendered in some script run, so its state is cleaned up. |
| h_new_session | 0.22 | 0.03 | strong | lost_after_page_reload=no | The selection is lost because the page is reloaded or reopened, which starts a new session. |

## Not asked again

- `lost_after_page_reload`: already stated (comment:c1: "No page reload, it happens on normal clicks.") -> lost_after_page_reload=no
- `widget_has_key`: already stated (body: "(not used in the code shared in this message)") -> widget_has_key=no
- `options_change_between_reruns`: already stated (comment:c1: "load_items() returns a set, so the options come in a different order each time.") -> options_change_between_reruns=yes

## Limitations

- h_widget_cleanup conflicts with reported facts: widget_has_key=no.
- h_new_session conflicts with reported facts: lost_after_page_reload=no.
