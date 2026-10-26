"""Dashboard local en català. Execució amb el launcher, no amb hosting cloud."""

from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import pandas as pd
import plotly.express as px
import streamlit as st

from garmin_running.desktop.controller import CONTRACT_VALIDATED, DesktopController
from garmin_running.desktop.credentials import CredentialUnavailable
from garmin_running.desktop.local import LocalPaths
from garmin_running.desktop.views import display_frame, pace_text, summary_frame, training_totals
from garmin_running.physiology.friel import heart_rate_zones, sensor_quality, time_in_zones
from garmin_running.storage.repository import Repository
from garmin_running.vdot.vdot_engine import (
    RUN_DISTANCES,
    current_performance,
    equivalent_seconds,
    interval_estimates,
    training_estimates,
    vdot,
)

st.set_page_config(page_title="Garmin Running Analytics", page_icon="🏃", layout="wide")


@st.cache_resource
def runtime(root):
    paths = LocalPaths(Path(root)).ensure()
    repository = Repository(paths.database_url, paths.root)
    return repository, DesktopController(paths)


@st.cache_data(show_spinner=False, max_entries=4)
def load_summaries(root, revision):
    repository, _ = runtime(root)
    return summary_frame(repository.summaries())


@st.cache_data(show_spinner=False, max_entries=2)
def load_activity(root, activity_id, version):
    repository, _ = runtime(root)
    return repository.activity(activity_id)


def selected_activity(activity_id):
    return load_activity(str(paths.root), activity_id, repository.activity_revision(activity_id))


paths = LocalPaths.discover().ensure()
repository, controller = runtime(str(paths.root))
settings = controller.preferences.load()
if controller.preferences.error:
    st.warning("Preferències no llegibles; s'obre l'historial sense autorització de xarxa")
state = controller.snapshot()
# Només resums lleugers. Els registres d'una activitat es carreguen sota demanda.
frame = load_summaries(str(paths.root), state.revision)

st.title("Garmin Running Analytics")
st.caption("Historial privat al teu ordinador · Running · Unitats mètriques")
with st.sidebar:
    st.subheader("El teu entrenament")
    page = st.radio(
        "Navegació",
        [
            "Resum",
            "Historial",
            "Detall d'activitat",
            "Joe Friel",
            "Jack Daniels VDOT",
            "Qualitat de dades",
            "Configuració",
        ],
    )
    st.caption("Servidor només a 127.0.0.1 · Sense serveis de pagament")


@st.fragment(run_every=2)
def sync_panel():
    current = controller.snapshot()
    busy = current.phase in {"syncing", "importing"}
    left, middle, right = st.columns([3, 1, 1])
    with left:
        st.caption(f"Connexió: {current.connection}")
        st.write(current.message)
        if busy:
            st.caption(
                f"Pàgines: {current.pages} · Noves: {current.new} · "
                f"Actualitzades: {current.updated} · Errors: {current.errors}"
            )
        if current.last_sync:
            st.caption(f"Última sincronització (UTC): {current.last_sync}")
    with middle:
        if st.button("Sincronitzar ara", disabled=busy):
            controller.start_sync()
            st.rerun(scope="fragment")
    with right:
        if st.button("Interrompre", disabled=current.phase != "syncing"):
            controller.cancel()
            st.rerun(scope="fragment")
    previous = st.session_state.get("rendered_revision", current.revision)
    st.session_state["rendered_revision"] = current.revision
    if current.revision != previous:
        st.rerun()


sync_panel()

if page == "Resum":
    if frame.empty:
        st.info(
            "Encara no hi ha activitats. Obre Configuració per importar un FIT o una exportació."
        )
    else:
        totals = training_totals(frame)
        cols = st.columns(4)
        cols[0].metric(
            "Quilòmetres de running", f"{totals['km']:.1f} km" if totals["km"] is not None else "—"
        )
        cols[1].metric(
            "Hores d'entrenament",
            f"{totals['hours']:.1f} h" if totals["hours"] is not None else "—",
        )
        cols[2].metric("Ritme mitjà ponderat", pace_text(totals["pace"]))
        cols[3].metric("Activitats locals", len(frame))
        left, right = st.columns(2)
        left.plotly_chart(
            px.bar(totals["weekly"], x="Setmana", y="km", title="Volum setmanal"), width="stretch"
        )
        right.plotly_chart(
            px.bar(totals["monthly"], x="Mes", y="km", title="Volum mensual"), width="stretch"
        )
        st.subheader("Activitats recents")
        st.dataframe(display_frame(frame).head(10), hide_index=True, width="stretch")
        st.caption("Agrupació en UTC. Ritme = segons de timer / km, només on hi ha ambdues dades.")

elif page == "Historial":
    left, right = st.columns(2)
    earliest = frame["Data"].min().date() if frame["Data"].notna().any() else date.today()
    start = left.date_input("Des de", value=earliest)
    end = right.date_input("Fins a", value=date.today())
    number = st.number_input("Pàgina de 100 activitats", min_value=1, value=1, step=1)
    rows = repository.summaries(
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        limit=100,
        offset=(number - 1) * 100,
        include_undated=True,
    )
    shown = summary_frame(rows)
    st.dataframe(display_frame(shown), hide_index=True, width="stretch")
    st.caption("Filtres inclusius per dia UTC. No es carreguen les sèries FIT de la taula.")

elif page == "Detall d'activitat":
    earliest = frame["Data"].min().date() if frame["Data"].notna().any() else date.today()
    left, right = st.columns(2)
    first = left.date_input("Detall des de", value=earliest)
    last = right.date_input("Detall fins a", value=date.today())
    choices = repository.summaries(
        start=first.isoformat(),
        end=(last + timedelta(days=1)).isoformat(),
        limit=500,
        include_undated=True,
    )
    if not choices:
        st.info("Importa una activitat per revisar-ne el detall.")
    else:
        labels = {
            r["id"]: f"{r['start'] or 'Sense data'} · {r['sport']} · "
            + (
                f"{r['metrics']['distance_m'] / 1000:.2f} km"
                if r["metrics"].get("distance_m") is not None
                else "Distància no disponible"
            )
            for r in choices
        }
        chosen = st.selectbox("Activitat (500 més recents)", list(labels), format_func=labels.get)
        activity = selected_activity(chosen)
        metrics = activity["metrics"]
        top = st.columns(3)
        distance = metrics.get("distance_m")
        top[0].metric("Distància", f"{distance / 1000:.2f} km" if distance is not None else "—")
        top[1].metric("Ritme mitjà", pace_text(metrics.get("avg_pace_seconds_per_km")))
        ascent = metrics.get("ascent_m")
        top[2].metric("Desnivell positiu", f"{ascent:.0f} m" if ascent is not None else "—")
        with st.expander("Mètriques i procedència del FIT"):
            st.json(metrics)
        records = pd.DataFrame(activity["samples"])
        if not records.empty:
            records["timestamp"] = pd.to_datetime(records["timestamp"], utc=True)
            for column, label in [
                ("heart_rate", "Freqüència cardíaca · BPM"),
                ("pace_seconds_per_km", "Ritme · min/km"),
                ("cadence", "Cadència · unitat original"),
                ("altitude_m", "Altitud · m"),
            ]:
                if column in records and records[column].notna().any():
                    # Tallar línies a buits >10 s evita una continuïtat visual inventada.
                    plotted = records[["timestamp", column]].copy()
                    plotted.loc[plotted.timestamp.diff().dt.total_seconds() > 10, column] = None
                    figure = px.line(plotted, x="timestamp", y=column, title=label)
                    if column == "pace_seconds_per_km":
                        values = plotted[column].dropna()
                        import math

                        low, high = (
                            (int(values.min()), int(values.max())) if not values.empty else (0, 0)
                        )
                        step = max(30, math.ceil((high - low + 1) / 300) * 30)
                        ticks = list(range((low // step) * step, high + step + 1, step))
                        figure.update_yaxes(
                            tickvals=ticks,
                            ticktext=[f"{v // 60}:{v % 60:02d}" for v in ticks],
                            title="min/km",
                        )
                    st.plotly_chart(figure, width="stretch")
            st.subheader("Qualitat del sensor òptic · indicadors descriptius")
            st.json(sensor_quality(activity))
            st.caption("Coincidència amb cadència no demostra error. No s'han corregit mostres.")
        else:
            st.warning("Activitat sense registres temporals; només es pot veure el resum.")
        st.subheader("Voltes i intervals")
        st.dataframe(pd.DataFrame(activity["laps"]), width="stretch")
        with st.expander("Esdeveniments, pauses i flags originals"):
            st.json({"events": activity["events"], "flags": activity["flags"]})

elif page == "Joe Friel":
    st.caption("Perfil clàssic running sol·licitat; separat de la revisió Friel de 2025")
    thresholds = settings["thresholds"]
    if not thresholds:
        st.info("LTHR no determinat. Introdueix un llindar validat a Configuració.")
    else:
        selected = st.selectbox(
            "Versió de llindar",
            range(len(thresholds)),
            index=len(thresholds) - 1,
            format_func=lambda i: f"{thresholds[i]['date']} · {thresholds[i]['bpm']} BPM",
        )
        threshold = thresholds[selected]
        st.metric("LTHR manual validat", f"{threshold['bpm']} BPM")
        st.caption(f"Procedència: {threshold['source']}")
        st.dataframe(pd.DataFrame(heart_rate_zones(threshold["bpm"])), hide_index=True)
        st.plotly_chart(
            px.line(
                pd.DataFrame(thresholds),
                x="date",
                y="bpm",
                markers=True,
                title="Versions de LTHR introduïdes",
            ),
            width="stretch",
        )
        if not frame.empty:
            chosen = st.selectbox(
                "Activitat per calcular temps en zona",
                frame["id"].head(500),
                format_func=lambda key: str(frame.set_index("id").loc[key, "Data"]),
            )
            activity = selected_activity(chosen)
            result = time_in_zones(activity, threshold["bpm"], settings["max_gap_seconds"])
            zone_frame = pd.DataFrame(
                {"Zona": list(result["seconds"]), "Segons": list(result["seconds"].values())}
            )
            st.plotly_chart(px.bar(zone_frame, x="Zona", y="Segons"), width="stretch")
            st.caption(f"Temps exclòs: {result['excluded_seconds']:.0f} s. {result['policy']}")
            if activity["start"] and activity["start"][:10] < threshold["date"]:
                st.warning(
                    "Llindar posterior a l'activitat: comparació retrospectiva, amb limitacions."
                )
            st.json(sensor_quality(activity))
    st.caption(
        "No s'estima el LTHR a partir de la FC màxima. Les proves de camp automàtiques "
        "i l'avaluació completa del sensor resten pendents."
    )

elif page == "Jack Daniels VDOT":
    races = settings["races"]
    current = current_performance(races, date.today())
    if current is None:
        st.info("VDOT actual no determinat: cal una competició validada dels últims 90 dies.")
    else:
        score = vdot(current["distance_m"], current["seconds"])
        st.metric("VDOT estimat · Daniels–Gilbert", f"{score:.1f}")
        st.caption(
            f"Prova del {current['date']} · {current['distance_m'] / 1000:g} km · "
            f"{current['seconds']:g} s. Selecció: resultat validat més recent, no màxim històric."
        )
        equivalent = [
            {"Distància m": distance, "Temps estimat s": round(equivalent_seconds(score, distance))}
            for distance in RUN_DISTANCES
        ]
        st.dataframe(pd.DataFrame(equivalent), hide_index=True)
    if races:
        history = [
            {
                "Data": r["date"],
                "VDOT": vdot(r["distance_m"], r["seconds"]),
                "Activitat": r["activity_id"],
            }
            for r in races
            if r["validated"]
        ]
        st.dataframe(pd.DataFrame(history), hide_index=True)
        if history:
            st.plotly_chart(
                px.scatter(pd.DataFrame(history), x="Data", y="VDOT", title="Rendiments validats"),
                width="stretch",
            )
    st.subheader("Ritmes E / M / T / I / R")
    st.caption(
        "Derivació orientativa documentada: no reprodueix les taules oficials ni s'ha "
        "validat per regressió contra la calculadora V.O2."
    )
    if current and st.checkbox("Mostra estimacions de ritmes a partir del rendiment validat"):
        estimates = training_estimates(vdot(current["distance_m"], current["seconds"]))
        display = [
            {
                "Tipus": p["type"],
                "Ritme ràpid": pace_text(p["fast_s_per_km"]),
                "Ritme lent": pace_text(p["slow_s_per_km"]),
                "km/h mín": round(p["slow_kmh"], 2),
                "km/h màx": round(p["fast_kmh"], 2),
                "Estat": p["status"],
            }
            for p in estimates
        ]
        st.dataframe(pd.DataFrame(display), hide_index=True)
        st.dataframe(pd.DataFrame(interval_estimates(estimates)), hide_index=True)
        st.caption(
            "I: filtre local de 3–5 min; R: màxim local de 120 s; T: 1000 m o més. "
            "E/M són treball continu. No és una prescripció d'una sessió."
        )
    st.caption(
        "VDOT no és VO₂max de laboratori ni VO₂max Garmin. Els temps equivalents "
        "són estimacions, no prediccions garantides. No es fa scraping de V.O2."
    )

elif page == "Qualitat de dades":
    st.info("Cobertura no verificada: cal contrastar l'inventari amb l'exportació del compte.")
    # Resums sense lectures massives de samples. L'auditoria completa és una acció explícita.
    st.write(f"Activitats locals: {len(frame)}")
    if not frame.empty:
        st.dataframe(frame[frame["Flags"] != ""][["Data", "Esport", "Flags"]], hide_index=True)
    latest = repository.latest_sync()
    if latest:
        st.write(f"Última execució: {latest.status}")
        st.json(latest.audit, expanded=False)
    if st.button("Auditoria completa de cobertura (pot trigar)"):
        st.json(repository.coverage(), expanded=False)

elif page == "Configuració":
    st.subheader("1. Configuració local")
    st.code(str(paths.root))
    st.caption(
        "SQLite, originals, imports, staging, backups i logs persisteixen entre actualitzacions."
    )
    st.subheader("2. Clau segura de Garmin")
    if not CONTRACT_VALIDATED:
        st.warning(
            "La sincronització real continua bloquejada: falta validar el contracte complet. "
            "Pots importar i consultar tot l'historial local sense credencials."
        )
    with st.form("credential_form", clear_on_submit=True):
        api_key = st.text_input("Garmin Personal API Key", type="password", key="credential_input")
        if st.form_submit_button("Desar a Windows Credential Manager"):
            try:
                controller.credentials.save(api_key.strip())
                controller.preferences.save({"credential_configured": True})
                st.success("Clau desada al gestor de Windows. No s'ha fet cap connexió.")
            except CredentialUnavailable as exc:
                st.error(str(exc))
    if st.button("Eliminar la clau desada"):
        try:
            if controller.snapshot().phase == "syncing":
                controller.cancel()
            controller.credentials.delete()
            controller.preferences.save(
                {"credential_configured": False, "consent": False, "auto_sync": False}
            )
            st.success("Credencial eliminada i consentiment revocat")
        except CredentialUnavailable as exc:
            st.error(str(exc))
    with st.form("consent_form"):
        consent = st.checkbox(
            "Autoritzo la primera connexió i les sincronitzacions posteriors amb Garmin",
            value=settings["consent"],
        )
        automatic = st.checkbox(
            "Sincronitzar automàticament en obrir l'aplicació", value=settings["auto_sync"]
        )
        if st.form_submit_button("Desar autorització"):
            controller.configure_consent(consent, automatic)
            st.success("Preferències desades. El bloqueig del contracte té prioritat.")
    st.subheader("3. Importar historial sense connexió")
    uploaded = st.file_uploader("FIT o exportació ZIP de Garmin", type=["fit", "zip"])
    busy = controller.snapshot().phase != "idle"
    if st.button("Importar fitxer", disabled=uploaded is None or busy):
        destination = paths.root / "imports" / f"{uuid4()}{Path(uploaded.name).suffix.lower()}"
        destination.write_bytes(uploaded.getbuffer())
        controller.start_import(destination)
        st.success("Importació iniciada en segon pla")
    source = st.text_input("O ruta local d'un directori/FIT/ZIP")
    if st.button("Importar ruta local", disabled=not source or busy):
        if Path(source).exists():
            controller.start_import(Path(source))
        else:
            st.error("La ruta no existeix")
    st.subheader("4. Llindar cardíac validat")
    with st.form("lthr_form"):
        bpm = st.number_input("LTHR · BPM", 60, 230, value=None, placeholder="Llindar validat")
        when = st.date_input("Data del llindar", value=date.today(), max_value=date.today())
        origin = st.text_input("Procedència del llindar")
        confirmed = st.checkbox("Confirmo que és un LTHR validat, no FC màxima")
        gap = st.number_input(
            "Buit màxim admès entre mostres · s", 1, 60, int(settings["max_gap_seconds"])
        )
        if st.form_submit_button("Desar versió de LTHR"):
            if confirmed and origin.strip() and bpm is not None:
                versions = [
                    *settings["thresholds"],
                    {"bpm": bpm, "date": when.isoformat(), "source": origin.strip()},
                ]
                controller.preferences.save({"thresholds": versions, "max_gap_seconds": gap})
                st.success("Versió desada; no s'ha modificat cap mesura original")
            else:
                st.error("Cal indicar procedència i confirmar el llindar")
    st.subheader("5. Competició o prova màxima validada")
    if not frame.empty:
        with st.form("race_form"):
            selected = st.selectbox(
                "Activitat d'origen",
                frame["id"].head(500),
                format_func=lambda key: str(frame.set_index("id").loc[key, "Data"]),
            )
            race_date = st.date_input("Data del resultat", max_value=date.today())
            distance = st.number_input(
                "Distància oficial · m",
                1500.0,
                42195.0,
                value=None,
                placeholder="Distància oficial confirmada",
            )
            seconds = st.number_input(
                "Temps oficial total · s (inclou pauses)",
                180.0,
                36000.0,
                value=None,
                placeholder="Temps oficial confirmat",
            )
            verified = st.checkbox("Confirmo distància, temps total i esforç màxim")
            if st.form_submit_button("Validar resultat per VDOT"):
                if verified and distance is not None and seconds is not None:
                    try:
                        vdot(distance, seconds)
                        races = [
                            *settings["races"],
                            {
                                "id": str(uuid4()),
                                "activity_id": selected,
                                "date": race_date.isoformat(),
                                "distance_m": distance,
                                "seconds": seconds,
                                "validated": True,
                                "method": "Daniels-Gilbert-1979-v1",
                            },
                        ]
                        controller.preferences.save({"races": races})
                        st.success("Resultat validat explícitament")
                    except ValueError as exc:
                        st.error(str(exc))
                else:
                    st.error("Cal validar el rendiment; no es fa servir un rodatge suau")
    with st.expander("Backups locals"):
        if st.button("Crear còpia de seguretat local", disabled=busy):
            controller.start_backup()
            st.success("Còpia iniciada en segon pla")
        st.caption(
            "Tanca l'aplicació abans de copiar la carpeta de dades completa. "
            "Fes una segona còpia en un disc USB xifrat que controlis. "
            "No es puja res a GitHub ni a serveis externs."
        )

# L'historial ja s'ha consultat i renderitzat abans de programar qualsevol treball.
controller.maybe_auto_start()
