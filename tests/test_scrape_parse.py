from ues_bot.scrape import (
    assignment_is_submitted,
    enrich_from_event_page,
    find_assignment_url,
    parse_events_from_dashboard,
    parse_grading_status,
    _parse_upcoming_events,
    _parse_timeline_items,
)
from bs4 import BeautifulSoup


# ---- Realistic HTML from the live UES Moodle dashboard ----

# "Eventos próximos" block HTML (server-rendered).
UPCOMING_BLOCK_HTML = """
<div class="event d-flex border-bottom pt-2 pb-3" data-eventtype-course="1" data-region="event-item">
  <div class="activityiconcontainer small assessment courseicon mr-3">
    <img alt="Evento de actividad" src="/theme/image.php/moove/assign/1770133833/monologo" class="icon">
  </div>
  <div class="overflow-auto">
    <h6 class="d-flex mb-1">
      <a class="text-truncate" data-type="event" data-action="view-event" data-event-id="101854"
         href="https://ueslearning.ues.mx/calendar/view.php?view=day&amp;course=11904&amp;time=1772605260#event_101854">
        Act 8: Investigación de conceptos. está en fecha de entrega
      </a>
    </h6>
    <div class="date small">
      <a href="https://ueslearning.ues.mx/calendar/view.php?view=day&amp;time=1772605260">Hoy</a>, 23:21
    </div>
  </div>
</div>
<div class="event d-flex border-bottom pt-2 pb-3" data-eventtype-course="1" data-region="event-item">
  <div class="activityiconcontainer small assessment courseicon mr-3">
    <img alt="Evento de actividad" src="/theme/image.php/moove/assign/1770133833/monologo" class="icon">
  </div>
  <div class="overflow-auto">
    <h6 class="d-flex mb-1">
      <a class="text-truncate" data-type="event" data-action="view-event" data-event-id="101838"
         href="https://ueslearning.ues.mx/calendar/view.php?view=day&amp;course=11944&amp;time=1773039540#event_101838">
        Act 13: Resumen del Modelo OSI. está en fecha de entrega
      </a>
    </h6>
    <div class="date small">
      <a href="https://ueslearning.ues.mx/calendar/view.php?view=day&amp;time=1773039540">domingo, 8 marzo</a>, 23:59
    </div>
  </div>
</div>
"""

# "Línea de tiempo" block HTML (JS-rendered).
TIMELINE_BLOCK_HTML = """
<div class="list-group-item timeline-event-list-item flex-column pt-2 pb-0 border-0 px-2"
     data-region="event-list-item">
  <div class="d-flex flex-wrap pb-1">
    <div class="d-flex mr-auto pb-1 mw-100 timeline-name">
      <small class="text-right text-nowrap align-self-center ml-1">23:59</small>
      <div class="activityiconcontainer small assessment courseicon mx-3">
        <img alt="Evento de actividad" src="/theme/image.php/moove/assign/1770133833/monologo" class="icon">
      </div>
      <div class="event-name-container flex-grow-1 line-height-3 nowrap text-truncate">
        <div class="d-flex">
          <h6 class="event-name mb-0 pb-1 text-truncate">
            <a href="https://ueslearning.ues.mx/mod/assign/view.php?id=479843"
               title="Act 13: Resumen del Modelo OSI. está en fecha de entrega"
               aria-label="Act 13: Resumen del Modelo OSI. actividad en IS N Redes de Computo 001 está pendiente para 8 de marzo de 2026, 23:59">
              Act 13: Resumen del Modelo OSI.</a>
          </h6>
        </div>
        <small class="mb-0">Tarea está en fecha de entrega · IS N Redes de Computo 001</small>
      </div>
    </div>
    <div class="d-flex timeline-action-button">
      <h6 class="event-action">
        <a class="btn btn-outline-secondary btn-sm" href="https://ueslearning.ues.mx/mod/assign/view.php?id=479843&amp;action=editsubmission">
          Añadir envío
        </a>
      </h6>
    </div>
  </div>
</div>
"""

# Combined dashboard with both blocks
FULL_DASHBOARD_HTML = f"<html><body>{UPCOMING_BLOCK_HTML}{TIMELINE_BLOCK_HTML}</body></html>"

# Legacy test HTML (simple form)
LEGACY_DASHBOARD_HTML = """
<div class="event" data-region="event-item">
  <h6><a data-action="view-event" data-event-id="42" href="http://x.com?event=42">Tarea 1</a></h6>
  <div class="date small"><a>2026-03-01</a></div>
</div>
<div class="event" data-region="event-item">
  <h6><a data-action="view-event" data-event-id="43" href="http://x.com?event=43">Tarea 2</a></h6>
  <div class="date small"><a>2026-03-05</a></div>
</div>
"""


# ---------------------------------------------------------------------------
# parse_events_from_dashboard (merged)
# ---------------------------------------------------------------------------

def test_parse_events_from_dashboard_legacy():
    """Backward compat: the old simple HTML still works."""
    events = parse_events_from_dashboard(LEGACY_DASHBOARD_HTML)
    assert len(events) == 2
    assert events[0].event_id == "42"
    assert events[0].title == "Tarea 1"
    assert events[1].event_id == "43"


def test_parse_events_from_empty_dashboard():
    events = parse_events_from_dashboard("<html><body></body></html>")
    assert events == []


def test_parse_full_dashboard_merges_blocks():
    """Events from both blocks are merged; timeline enriches upcoming."""
    events = parse_events_from_dashboard(FULL_DASHBOARD_HTML)
    # 2 upcoming + 1 timeline, but Act 13 exists in both → merged
    assert len(events) == 2

    act13 = [e for e in events if "Act 13" in e.title]
    assert len(act13) == 1
    e = act13[0]
    # Enriched from the timeline block:
    assert e.course_name == "IS N Redes de Computo 001"
    assert "479843" in e.assignment_url


def test_parse_dashboard_timeline_only():
    """Dashboard with only timeline items (no upcoming block)."""
    events = parse_events_from_dashboard(f"<html><body>{TIMELINE_BLOCK_HTML}</body></html>")
    assert len(events) == 1
    assert events[0].course_name == "IS N Redes de Computo 001"
    assert "mod/assign/view.php?id=479843" in events[0].url


def test_parse_dashboard_upcoming_only():
    """Dashboard with only upcoming block (timeline hasn't loaded)."""
    events = parse_events_from_dashboard(f"<html><body>{UPCOMING_BLOCK_HTML}</body></html>")
    assert len(events) == 2
    assert events[0].event_id == "101854"
    assert events[1].event_id == "101838"


# ---------------------------------------------------------------------------
# _parse_upcoming_events
# ---------------------------------------------------------------------------

def test_parse_upcoming_extracts_event_id_from_hash():
    soup = BeautifulSoup(UPCOMING_BLOCK_HTML, "html.parser")
    events = _parse_upcoming_events(soup)
    assert events[0].event_id == "101854"
    assert events[1].event_id == "101838"


def test_parse_upcoming_extracts_due_text():
    soup = BeautifulSoup(UPCOMING_BLOCK_HTML, "html.parser")
    events = _parse_upcoming_events(soup)
    assert "Hoy" in events[0].due_text
    assert "23:21" in events[0].due_text
    assert "domingo" in events[1].due_text


# ---------------------------------------------------------------------------
# _parse_timeline_items
# ---------------------------------------------------------------------------

def test_parse_timeline_extracts_course_from_aria():
    soup = BeautifulSoup(TIMELINE_BLOCK_HTML, "html.parser")
    events = _parse_timeline_items(soup)
    assert len(events) == 1
    assert events[0].course_name == "IS N Redes de Computo 001"


def test_parse_timeline_extracts_due_from_aria():
    soup = BeautifulSoup(TIMELINE_BLOCK_HTML, "html.parser")
    events = _parse_timeline_items(soup)
    assert "8 de marzo de 2026, 23:59" in events[0].due_text


def test_parse_timeline_extracts_assignment_url():
    soup = BeautifulSoup(TIMELINE_BLOCK_HTML, "html.parser")
    events = _parse_timeline_items(soup)
    assert "mod/assign/view.php?id=479843" in events[0].assignment_url
    # Should NOT contain &action=editsubmission
    assert "action=editsubmission" not in events[0].assignment_url


def test_parse_timeline_course_fallback_to_subtitle():
    """When aria-label doesn't have course, extract from subtitle."""
    html = """
    <div data-region="event-list-item">
      <div class="d-flex mr-auto timeline-name">
        <small>10:00</small>
        <div class="event-name-container">
          <h6 class="event-name">
            <a href="/mod/assign/view.php?id=999" aria-label="Tarea X">Tarea X</a>
          </h6>
          <small>Tarea está en fecha de entrega · Curso ABC 001</small>
        </div>
      </div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    events = _parse_timeline_items(soup)
    assert events[0].course_name == "Curso ABC 001"


# ---------------------------------------------------------------------------
# assignment_is_submitted
# ---------------------------------------------------------------------------

def test_assignment_is_submitted_detected():
    html = '<table class="generaltable"><tr><th>Submission status</th><td class="submissionstatussubmitted">Submitted for grading</td></tr></table>'
    submitted, _status = assignment_is_submitted(html)
    assert submitted is True


def test_assignment_is_submitted_detected_real():
    """Real HTML from the live assignment page."""
    html = '''
    <table class="generaltable table-bordered">
      <tr><th class="cell c0">Estatus de la entrega</th>
          <td class="submissionstatussubmitted cell c1 lastcol">Enviado para calificar</td></tr>
      <tr><th class="cell c0">Estatus de calificación</th>
          <td class="submissionnotgraded cell c1 lastcol">No calificado</td></tr>
    </table>
    '''
    submitted, status = assignment_is_submitted(html)
    assert submitted is True
    assert "Enviado para calificar" in status


def test_assignment_is_submitted_not_submitted():
    html = '<table class="generaltable"><tr><th>Submission status</th><td class="submissionstatusnosubmission">No submission</td></tr></table>'
    submitted, _status = assignment_is_submitted(html)
    assert submitted is False


def test_assignment_is_submitted_not_submitted_plain_text():
    html = '<table class="generaltable"><tr><th>Submission status</th><td>Not submitted</td></tr></table>'
    submitted, _status = assignment_is_submitted(html)
    assert submitted is False


def test_assignment_is_submitted_estado_del_envio():
    """Match the 'Estado del envío' variant seen in some Moodle themes."""
    html = '<table class="generaltable"><tr><th>Estado del envío</th><td>No enviado</td></tr></table>'
    submitted, status = assignment_is_submitted(html)
    assert submitted is False


def test_assignment_is_submitted_unknown():
    html = "<html><body>Nothing here</body></html>"
    submitted, status = assignment_is_submitted(html)
    assert submitted is None
    assert status == "No detectado"


# ---------------------------------------------------------------------------
# find_assignment_url
# ---------------------------------------------------------------------------

def test_find_assignment_url():
    html = '<a href="https://ueslearning.ues.mx/mod/assign/view.php?id=100">Ver</a>'
    url = find_assignment_url(html, base="https://ueslearning.ues.mx")
    assert url == "https://ueslearning.ues.mx/mod/assign/view.php?id=100"


def test_find_assignment_url_not_found():
    html = '<a href="https://other.com/page">Link</a>'
    url = find_assignment_url(html, base="https://ueslearning.ues.mx")
    assert url == ""


def test_find_assignment_url_prefers_card_link():
    """The card-footer 'Ir a la actividad' link should be preferred."""
    html = """
    <a href="https://ueslearning.ues.mx/mod/forum/view.php?id=50">Forum</a>
    <a class="card-link" href="https://ueslearning.ues.mx/mod/assign/view.php?id=100">Ir a la actividad</a>
    <a href="https://ueslearning.ues.mx/mod/assign/view.php?id=200">Another</a>
    """
    url = find_assignment_url(html, base="https://ueslearning.ues.mx")
    assert url == "https://ueslearning.ues.mx/mod/assign/view.php?id=100"


# ---------------------------------------------------------------------------
# enrich_from_event_page
# ---------------------------------------------------------------------------

def test_enrich_from_event_page():
    html = """
    <a href="/course/view.php?id=5">Calculo II</a>
    <div class="description-content">Entregar ejercicios del capitulo 3.</div>
    """
    course, desc = enrich_from_event_page(html)
    assert course == "Calculo II"
    assert "capitulo 3" in desc


def test_enrich_from_event_page_skips_generic_labels():
    """The course name extractor should skip section labels like 'General'."""
    html = """
    <a href="/course/view.php?id=11904#section-0">General</a>
    <a href="/course/view.php?id=11904#section-2">Elemento de Competencia 2</a>
    <a href="/course/view.php?id=11904">IS N Auditoria en Informatica 001</a>
    <div class="description-content">Descripción de la tarea.</div>
    """
    course, desc = enrich_from_event_page(html)
    assert course == "IS N Auditoria en Informatica 001"


def test_enrich_from_event_page_no_course():
    html = '<div class="description-content">Sin materia asociada.</div>'
    course, desc = enrich_from_event_page(html)
    assert course == "Sin materia"
    assert "Sin materia asociada" in desc


# ---------------------------------------------------------------------------
# parse_grading_status
# ---------------------------------------------------------------------------

def test_parse_grading_status_not_graded():
    html = '''
    <table class="generaltable table-bordered">
      <tr><th>Estatus de la entrega</th><td class="submissionstatussubmitted">Enviado</td></tr>
      <tr><th>Estatus de calificación</th><td class="submissionnotgraded">No calificado</td></tr>
    </table>
    '''
    assert parse_grading_status(html) == "No calificado"


def test_parse_grading_status_graded():
    html = '''
    <table class="generaltable">
      <tr><th>Grading status</th><td>Graded</td></tr>
    </table>
    '''
    assert parse_grading_status(html) == "Graded"


def test_parse_grading_status_missing():
    html = '<html><body>Nothing here</body></html>'
    assert parse_grading_status(html) == ""


