# Case part1-demo-session-state: next step

**Decision:** Escalate / refer

No explanation is decisive (best: unlisted_cause at 0.19) and no available question or check separates the remaining ones. Refer the case with the evidence collected so far.

## Next steps

1. **[question]** Please paste the full error message or traceback, from the terminal running Streamlit and from the browser console if any.
   - facet `error_message`, gain 0.000 bits, cost 1
   - why: Not stated in the case; needed to continue the investigation (exact error message / traceback).
2. **[question]** Where does the failing app run: your own machine, Streamlit Community Cloud, a Docker container, Kubernetes, a platform such as Heroku/Cloud Run, or your own server/VM?
   - facet `deployment_target`, gain 0.000 bits, cost 1
   - why: Not stated in the case; needed to continue the investigation (where the failing app runs).

## Known facts

| facet | value | source | quote |
|---|---|---|---|
| streamlit_version | 1.64.0 | body | Environment: Python 3.11, Streamlit 1.64.0, Chrome. |
| python_version | 3.11 | body | Environment: Python 3.11, Streamlit 1.64.0, Chrome. |
| browser | chrome | body | Environment: Python 3.11, Streamlit 1.64.0, Chrome. |
| regression | yes | body | After upgrading to 1.64.0, st.session_state values set inside a callback disappear on the next rerun. |
| uses_callback | yes | body | After upgrading to 1.64.0, st.session_state values set inside a callback disappear on the next rerun. |
| code_snippet | present | body | ```python |
| inside_fragment | no | body | (not used in the code shared in this message) |
| inside_dialog | no | body | (not used in the code shared in this message) |
| inside_form | no | body | (not used in the code shared in this message) |
| calls_st_rerun | no | body | (not used in the code shared in this message) |
| multipage_app | no | body | (not used in the code shared in this message) |
| widget_has_key | no | body | (not used in the code shared in this message) |

## Hypotheses

| id | prior | posterior | evidence | conflicts | statement |
|---|---|---|---|---|---|
| unlisted_cause | 0.20 | 0.19 | none | - | A cause that none of the retrieved evidence describes. |
| h3 | 0.09 | 0.14 | weak | - | _value  increment = st.button('Increment', on_click=increment_counter,     args=(increment_value, ))  st.write('Count = ', st.session_state.count) ```  Additionally, we can also... |
| h5 | 0.08 | 0.13 | weak | - | st.button('Increment', on_click=increment_counter)  st.write('Count = ', st.session_state.count) ```  Now, pressing the **_Increment_** button updates the count each time by cal... |
| h1 | 0.09 | 0.09 | weak | - | et's move on to something a little more complex. |
| h2 | 0.09 | 0.08 | weak | - | mples that illustrate how to add Session State to our Counter app. |
| h4 | 0.08 | 0.08 | weak | - | existing session is lost and a new one created, causing unpleasant/unexpected user experience. |
| h7 | 0.07 | 0.07 | weak | - | om_proto` re-imports that frontend value into session state, undoing the delete. |
| h8 | 0.07 | 0.07 | weak | - | the consequence is that it can result in a seemingly invalid state. |
| h9 | 0.07 | 0.07 | weak | - | de a Session State variable across app reruns. |
| h10 | 0.07 | 0.07 | strong | - | _state:     # set the initial default value of the slider widget     st.session_state.celsius = 50.0  st.slider(     "Temperature in Celsius",     min_value=-100.0,     max_valu... |
| h6 | 0.08 | 0.04 | weak | inside_form=no | ement_value=5))  st.button('Decrement', on_click=decrement_counter, 	kwargs=dict(decrement_value=1))  st.write('Count = ', st.session_state.count) ```  ### Example 4: Forms and ... |

## Still unknown

- `lost_after_page_reload`: Whether state is lost only after a browser reload / new tab / reconnect (relevant to h4; gain 0.028)

## Not asked again

- `uses_callback`: already stated (body: "After upgrading to 1.64.0, st.session_state values set inside a callback disappear on the next rerun.") -> uses_callback=yes
- `inside_form`: already stated (body: "(not used in the code shared in this message)") -> inside_form=no

## Limitations

- Part 1: No matching release note found – version that introduced/fixed the issue is unknown.
- h1, h2, h7, h8, h9, h10: no testable prediction, so no question can confirm or rule them out.
- h6 conflicts with reported facts: inside_form=no.
- The leading explanation h3 rests only on similar reports; a similar report does not prove the same root cause.
