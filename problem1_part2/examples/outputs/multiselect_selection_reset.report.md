# Case example-multiselect-reset: next step

**Decision:** Request information

No explanation is clearly ahead (h_widget_identity, h_new_session, unlisted_cause remain plausible). The steps below are the ones whose answers best separate them per unit of user effort.

## Next steps

1. **[question]** Is the value lost only after a full browser reload, opening the app in a new tab or a reconnect, or also during normal interaction without reloading?
   - facet `lost_after_page_reload`, gain 0.252 bits, cost 1
   - why: 'yes' favours h_new_session, an unlisted cause; 'no' favours h_widget_identity, h_widget_cleanup
2. **[question]** Do the widget's label, options (or their order), default value or `format_func` output change from one rerun to the next?
   - facet `options_change_between_reruns`, gain 0.103 bits, cost 2
   - why: 'yes' favours h_widget_identity; 'no' favours h_new_session, h_widget_cleanup, an unlisted cause

## Known facts

| facet | value | source | quote |
|---|---|---|---|
| streamlit_version | 1.52.0 | body | - Streamlit version: 1.52.0 |
| python_version | 3.12 | body | - Python version: 3.12 |
| browser | firefox | body | - Browser: Firefox |
| code_snippet | present | body | ```python |
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
| h_widget_identity | 0.40 | 0.59 | strong | - | The multiselect has no key and its options come in a different order on each rerun, so it gets a new identity and resets. |
| h_new_session | 0.22 | 0.19 | strong | - | The selection is lost because the page is reloaded or reopened, which starts a new session. |
| unlisted_cause | 0.20 | 0.17 | none | - | A cause that none of the retrieved evidence describes. |
| h_widget_cleanup | 0.18 | 0.05 | strong | widget_has_key=no | The keyed widget is not rendered in some script run, so its state is cleaned up. |

## Still unknown

- `lost_after_page_reload`: Whether state is lost only after a browser reload / new tab / reconnect (relevant to h_widget_identity, h_new_session, h_widget_cleanup; gain 0.252)
- `options_change_between_reruns`: Whether the widget's label, options, default or format_func output change between reruns (relevant to h_widget_identity; gain 0.103)

## Not asked again

- `widget_has_key`: already stated (body: "(not used in the code shared in this message)") -> widget_has_key=no

## Limitations

- h_widget_cleanup conflicts with reported facts: widget_has_key=no.
