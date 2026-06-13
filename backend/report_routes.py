"""
EduNexus — PDF Report Card Generator
GET /api/student/report  → streams a PDF file

Uses: reportlab (pip install reportlab)
"""

import io
import datetime
from flask import Blueprint, request, make_response
from reportlab.lib                  import colors
from reportlab.lib.pagesizes        import A4
from reportlab.lib.styles           import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units            import cm, mm
from reportlab.lib.enums            import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus             import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.graphics.shapes      import Drawing, Rect, Circle, Line, String
from reportlab.graphics             import renderPDF
from reportlab.pdfgen               import canvas as rl_canvas

from db              import get_db_connection
from auth_middleware import token_required

report_bp = Blueprint('report', __name__, url_prefix='/api/student')

# ── Brand palette (dark indigo + purple gradient feel, printable) ─────────────
C_PRIMARY   = colors.HexColor('#3730a3')   # indigo-800
C_ACCENT    = colors.HexColor('#6366f1')   # indigo-500
C_LIGHT     = colors.HexColor('#e0e7ff')   # indigo-100
C_DARK      = colors.HexColor('#1e1b4b')   # indigo-950
C_MUTED     = colors.HexColor('#64748b')   # slate-500
C_SUCCESS   = colors.HexColor('#059669')   # emerald-600
C_WARNING   = colors.HexColor('#d97706')   # amber-600
C_DANGER    = colors.HexColor('#dc2626')   # red-600
C_WHITE     = colors.white
C_OFF_WHITE = colors.HexColor('#f8fafc')
C_BORDER    = colors.HexColor('#cbd5e1')
C_ROW_ALT   = colors.HexColor('#f1f5f9')

PAGE_W, PAGE_H = A4      # 595.28 x 841.89 pts
MARGIN          = 1.8 * cm

# ── Grade helper ──────────────────────────────────────────────────────────────
GRADE_SCALE = [
    (90, 'A+', 10.0, C_SUCCESS),
    (80, 'A',   9.0, C_SUCCESS),
    (70, 'B+',  8.0, C_ACCENT),
    (60, 'B',   7.0, C_ACCENT),
    (50, 'C',   6.0, C_WARNING),
    (40, 'D',   5.0, C_WARNING),
    (0,  'F',   0.0, C_DANGER),
]

def get_grade(score):
    if score is None: return ('—', '—', C_MUTED)
    for threshold, grade, gp, col in GRADE_SCALE:
        if score >= threshold:
            return (grade, f'{gp:.1f}', col)
    return ('F', '0.0', C_DANGER)

# ── Canvas-level decorations (header band, footer, watermark) ─────────────────
class ReportCardCanvas(rl_canvas.Canvas):
    def __init__(self, filename, student_name='', reg_no='', **kw):
        super().__init__(filename, **kw)
        self.student_name = student_name
        self.reg_no       = reg_no
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page(num_pages)
            super().showPage()
        super().save()

    def _draw_page(self, total_pages):
        w, h = A4
        page_num = self._saved_page_states.index(dict(
            {k: self.__dict__[k] for k in self.__dict__ if k in self._saved_page_states[0]}
        )) + 1 if False else self._pageNumber

        # ── Top header band ──────────────────────────────────────────────────
        self.setFillColor(C_DARK)
        self.rect(0, h - 2.6*cm, w, 2.6*cm, fill=1, stroke=0)

        # Accent stripe
        self.setFillColor(C_ACCENT)
        self.rect(0, h - 2.6*cm, 0.4*cm, 2.6*cm, fill=1, stroke=0)

        # Institution name
        self.setFillColor(C_WHITE)
        self.setFont('Helvetica-Bold', 15)
        self.drawString(1.2*cm, h - 1.35*cm, 'EduNexus Academic Institution')

        self.setFont('Helvetica', 9)
        self.setFillColor(colors.HexColor('#a5b4fc'))
        self.drawString(1.2*cm, h - 1.9*cm, 'Academic Report Card  ·  Confidential Document')

        # Year badge (top-right)
        yr = datetime.datetime.now().year
        self.setFillColor(C_ACCENT)
        self.roundRect(w - 3.5*cm, h - 2.1*cm, 2.8*cm, 1.0*cm, 0.25*cm, fill=1, stroke=0)
        self.setFillColor(C_WHITE)
        self.setFont('Helvetica-Bold', 10)
        self.drawCentredString(w - 2.1*cm, h - 1.65*cm, f'A.Y. {yr}-{yr+1}')

        # ── Diagonal watermark ───────────────────────────────────────────────
        self.saveState()
        self.translate(w/2, h/2)
        self.rotate(45)
        self.setFont('Helvetica-Bold', 52)
        self.setFillColor(colors.HexColor('#e0e7ff'))
        self.setFillAlpha(0.12)
        self.drawCentredString(0, 0, 'EDUNEXUS')
        self.restoreState()

        # ── Bottom footer ────────────────────────────────────────────────────
        self.setFillColor(C_DARK)
        self.rect(0, 0, w, 1.4*cm, fill=1, stroke=0)
        self.setFillColor(C_ACCENT)
        self.rect(0, 0, w, 0.18*cm, fill=1, stroke=0)

        self.setFillColor(C_WHITE)
        self.setFont('Helvetica', 7.5)
        self.drawString(MARGIN, 0.65*cm, f'Generated: {datetime.datetime.now().strftime("%d %B %Y, %I:%M %p")}')
        self.drawString(MARGIN + 5*cm, 0.65*cm, f'Student: {self.student_name}  |  Reg. No: {self.reg_no}')

        self.setFont('Helvetica', 7.5)
        self.setFillColor(colors.HexColor('#a5b4fc'))
        self.drawRightString(w - MARGIN, 0.65*cm, f'Page {page_num} of {total_pages}  ·  EduNexus ERP')


# ── Data fetcher ──────────────────────────────────────────────────────────────
def _fetch_report_data(user_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        # 1 · Profile
        cur.execute("""
            SELECT s.register_number, u.name, u.email, u.id,
                   c.id AS class_id, c.section,
                   d.name AS department, sem.number AS semester,
                   i.name AS institution_name
            FROM Students s
            JOIN Users u         ON s.user_id = u.id
            LEFT JOIN Classes c  ON s.class_id = c.id
            LEFT JOIN Departments d ON c.department_id = d.id
            LEFT JOIN Semesters sem ON c.semester_id = sem.id
            LEFT JOIN Users fu   ON u.id = fu.id
            LEFT JOIN Institutions i ON u.institution_id = i.id
            WHERE s.user_id = %s
        """, (user_id,))
        profile = cur.fetchone()
        if not profile:
            return None, 'Student not found'

        class_id = profile['class_id']

        # 2 · Subjects
        cur.execute("""
            SELECT sub.id, sub.name, sub.code, u.name AS teacher_name
            FROM Subjects sub
            LEFT JOIN SubjectAssignments sa ON sub.id = sa.subject_id AND sa.class_id = %s
            LEFT JOIN Users u ON sa.teacher_id = u.id
            WHERE sub.class_id = %s
            ORDER BY sub.name
        """, (class_id, class_id))
        subjects = cur.fetchall()

        # 3 · Marks + attendance per subject
        subject_data = []
        total_present_all = 0
        total_hours_all   = 0

        for sub in subjects:
            # Marks grouped by type
            cur.execute("""
                SELECT mark_type, mark_name, marks
                FROM Marks
                WHERE subject_id = %s AND student_id = %s
                ORDER BY mark_type, mark_name
            """, (sub['id'], user_id))
            mark_rows = cur.fetchall()

            # Group by type
            by_type = {}
            for mr in mark_rows:
                mt = mr['mark_type']
                if mt not in by_type:
                    by_type[mt] = []
                by_type[mt].append({'name': mr['mark_name'], 'marks': float(mr['marks']) if mr['marks'] else 0.0})

            total_marks = sum(float(mr['marks']) for mr in mark_rows if mr['marks'])
            count_marks = len(mark_rows)
            avg_marks   = total_marks / count_marks if count_marks > 0 else None

            # Attendance
            cur.execute("""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status IN ('P','DL') THEN 1 ELSE 0 END) AS present
                FROM Attendance
                WHERE subject_id = %s AND student_id = %s AND class_id = %s
            """, (sub['id'], user_id, class_id))
            att = cur.fetchone()
            total_h   = att['total']   or 0
            present_h = att['present'] or 0
            att_pct   = round((present_h / total_h * 100), 1) if total_h > 0 else None

            total_present_all += present_h
            total_hours_all   += total_h

            subject_data.append({
                'name':         sub['name'],
                'code':         sub['code'] or '—',
                'teacher':      sub['teacher_name'] or 'Unassigned',
                'by_type':      by_type,
                'total_marks':  round(total_marks, 1),
                'count_marks':  count_marks,
                'average':      round(avg_marks, 2) if avg_marks is not None else None,
                'present':      present_h,
                'total_hours':  total_h,
                'att_pct':      att_pct,
            })

        # 4 · Overall stats
        scored_avgs = [s['average'] for s in subject_data if s['average'] is not None]
        overall_avg = round(sum(scored_avgs) / len(scored_avgs), 2) if scored_avgs else None
        overall_att = round((total_present_all / total_hours_all * 100), 1) if total_hours_all > 0 else None

        # 5 · GPA (4.0 scale average)
        gpa_points = []
        for avg in scored_avgs:
            _, _, gp_str, _ = GRADE_SCALE[0]
            for threshold, _, gp, _ in GRADE_SCALE:
                if avg >= threshold:
                    gpa_points.append(gp)
                    break
        overall_gpa = round(sum(gpa_points) / len(gpa_points), 2) if gpa_points else None

        return {
            'profile':       dict(profile),
            'subjects':      subject_data,
            'overall_avg':   overall_avg,
            'overall_att':   overall_att,
            'overall_gpa':   overall_gpa,
            'total_present': total_present_all,
            'total_hours':   total_hours_all,
        }, None

    finally:
        conn.close()


# ── PDF builder ───────────────────────────────────────────────────────────────
def build_pdf(data) -> bytes:
    buf     = io.BytesIO()
    profile = data['profile']
    name    = profile.get('name', 'Student')
    reg_no  = profile.get('register_number', '—')

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=3.2*cm, bottomMargin=2.2*cm,
        title=f'Report Card — {name}',
        author='EduNexus ERP',
        subject='Academic Report Card',
    )
    doc.canvasmaker = lambda *a, **kw: ReportCardCanvas(
        *a, student_name=name, reg_no=reg_no, **kw
    )

    styles = getSampleStyleSheet()

    def style(name_s, **kwargs):
        s = ParagraphStyle(name_s, **kwargs)
        return s

    # Custom paragraph styles
    TITLE = style('Title2', fontName='Helvetica-Bold', fontSize=16,
                  textColor=C_DARK, alignment=TA_CENTER, spaceAfter=4)
    SUBTITLE = style('Subtitle2', fontName='Helvetica', fontSize=10,
                     textColor=C_MUTED, alignment=TA_CENTER, spaceAfter=2)
    SECTION_HEAD = style('SHead', fontName='Helvetica-Bold', fontSize=11,
                         textColor=C_PRIMARY, spaceBefore=14, spaceAfter=6)
    CELL_BODY = style('CBody', fontName='Helvetica', fontSize=9,
                      textColor=C_DARK, leading=13)
    CELL_BOLD = style('CBold', fontName='Helvetica-Bold', fontSize=9,
                      textColor=C_DARK, leading=13)
    SMALL = style('Small', fontName='Helvetica', fontSize=8,
                  textColor=C_MUTED, leading=12)
    FOOTER_NOTE = style('FNote', fontName='Helvetica-Oblique', fontSize=8,
                        textColor=C_MUTED, alignment=TA_CENTER)

    story = []
    W = PAGE_W - 2 * MARGIN  # usable width

    # ─────────────────────────────────────────────────────────────────────────
    # Section 1 — Report Title
    # ─────────────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph('Academic Report Card', TITLE))
    story.append(Paragraph(
        f'{profile.get("department","—")} &nbsp;·&nbsp; Semester {profile.get("semester","—")} &nbsp;·&nbsp; Section {profile.get("section","—")}',
        SUBTITLE
    ))
    story.append(HRFlowable(width=W, color=C_BORDER, thickness=0.5, spaceAfter=12))

    # ─────────────────────────────────────────────────────────────────────────
    # Section 2 — Student Info Card
    # ─────────────────────────────────────────────────────────────────────────
    story.append(Paragraph('Student Information', SECTION_HEAD))

    def info_row(label, value):
        return [Paragraph(f'<b>{label}</b>', CELL_BOLD),
                Paragraph(str(value) if value else '—', CELL_BODY)]

    sem_roman = {1:'I',2:'II',3:'III',4:'IV',5:'V',6:'VI',7:'VII',8:'VIII'}
    sem_disp  = sem_roman.get(profile.get('semester'), str(profile.get('semester','—')))

    info_data = [
        info_row('Full Name',         profile.get('name','—')),
        info_row('Register Number',   profile.get('register_number','—')),
        info_row('Department',        profile.get('department','—')),
        info_row('Semester',          f'Semester {sem_disp}'),
        info_row('Section',           profile.get('section','—')),
        info_row('Email',             profile.get('email','—')),
        info_row('Date of Report',    datetime.datetime.now().strftime('%d %B %Y')),
    ]

    COL_LABEL = 4.5*cm
    COL_VAL   = W/2 - COL_LABEL - 0.3*cm

    # Two columns of info
    left_rows  = info_data[:4]
    right_rows = info_data[4:]

    def make_info_block(rows):
        t = Table(rows, colWidths=[COL_LABEL, COL_VAL])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (0,-1), C_LIGHT),
            ('ROWBACKGROUNDS', (0,0), (-1,-1), [C_WHITE, C_OFF_WHITE]),
            ('GRID', (0,0), (-1,-1), 0.4, C_BORDER),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TEXTCOLOR', (0,0), (0,-1), C_PRIMARY),
        ]))
        return t

    info_pair = Table(
        [[make_info_block(left_rows), Spacer(0.5*cm, 1), make_info_block(right_rows)]],
        colWidths=[W/2 - 0.25*cm, 0.5*cm, W/2 - 0.25*cm]
    )
    info_pair.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(info_pair)

    # ─────────────────────────────────────────────────────────────────────────
    # Section 3 — Performance Snapshot
    # ─────────────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph('Performance Snapshot', SECTION_HEAD))

    overall_avg = data['overall_avg']
    overall_gpa = data['overall_gpa']
    ov_att      = data['overall_att']
    ov_grade, _, ov_col = get_grade(overall_avg)

    def snap_cell(label, value, value_color=C_DARK, sub=''):
        val_para = Paragraph(f'<font name="Helvetica-Bold" size="18" color="#{value_color.hexval()[2:]}">{value}</font>', CELL_BODY)
        lbl_para = Paragraph(label, SMALL)
        sub_para = Paragraph(sub, SMALL) if sub else Spacer(0,0)
        return [val_para, lbl_para, sub_para]

    def snap_cell_simple(label, val, col=C_DARK, sub=''):
        hex_col = col.hexval()[2:] if hasattr(col, 'hexval') else '1e1b4b'
        content = f'<font name="Helvetica-Bold" size="17" color="#{hex_col}">{val}</font>'
        return Table(
            [[Paragraph(content, CELL_BODY)],
             [Paragraph(label, SMALL)],
             [Paragraph(sub, SMALL) if sub else Spacer(0, 0)]],
            colWidths=[W/4 - 0.3*cm]
        )

    snap_avg    = f'{overall_avg}%' if overall_avg is not None else 'N/A'
    snap_grade  = ov_grade
    snap_gpa    = f'{overall_gpa}/10' if overall_gpa is not None else 'N/A'
    snap_att    = f'{ov_att}%' if ov_att is not None else 'N/A'

    att_col = C_SUCCESS if (ov_att or 0) >= 75 else C_WARNING if (ov_att or 0) >= 60 else C_DANGER

    snap_cells = [
        snap_cell_simple('Overall Average', snap_avg, C_ACCENT if overall_avg else C_MUTED),
        snap_cell_simple('Overall Grade',   snap_grade, ov_col),
        snap_cell_simple('GPA (10 pt)',     snap_gpa, C_PRIMARY if overall_gpa else C_MUTED),
        snap_cell_simple('Attendance',      snap_att, att_col),
    ]
    snap_table = Table([snap_cells], colWidths=[W/4]*4)
    snap_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_LIGHT),
        ('BOX', (0,0), (-1,-1), 0.5, C_BORDER),
        ('LINEAFTER', (0,0), (2,-1), 0.5, C_BORDER),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(snap_table)

    # ─────────────────────────────────────────────────────────────────────────
    # Section 4 — Subject-wise Marks Table
    # ─────────────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph('Subject-wise Academic Marks', SECTION_HEAD))

    # Collect all mark types used across subjects
    all_types = []
    for sub in data['subjects']:
        for mt in sub['by_type']:
            if mt not in all_types:
                all_types.append(mt)

    # Build dynamic columns: Subject | Code | [type cols] | Total | Avg | Att% | Grade
    def ph(text, bold=False, align=TA_CENTER, color=C_WHITE, size=8.5):
        font = 'Helvetica-Bold' if bold else 'Helvetica'
        hex_c = color.hexval()[2:] if hasattr(color, 'hexval') else 'ffffff'
        return Paragraph(f'<font name="{font}" size="{size}" color="#{hex_c}">{text}</font>',
                         ParagraphStyle('ph', alignment=align, leading=12))

    header_row = [
        ph('Subject', True),
        ph('Code', True),
    ]
    for mt in all_types:
        header_row.append(ph(mt, True))
    header_row += [
        ph('Total', True),
        ph('Avg', True),
        ph('Att%', True),
        ph('Grade', True),
    ]

    # Column widths
    FIXED_COLS   = [4.0*cm, 1.4*cm] + [1.7*cm]*len(all_types) + [1.3*cm, 1.1*cm, 1.1*cm, 1.1*cm]
    usable = W
    total_fixed = sum(FIXED_COLS)
    if total_fixed > usable:
        # Shrink type columns proportionally
        overflow = total_fixed - usable
        for i in range(2, 2+len(all_types)):
            FIXED_COLS[i] -= overflow / len(all_types) if all_types else 0

    marks_rows = [header_row]

    for sub in data['subjects']:
        # Sum per type (combine all entries under same type)
        type_totals = {}
        for mt in all_types:
            if mt in sub['by_type']:
                type_totals[mt] = sum(e['marks'] for e in sub['by_type'][mt])
            else:
                type_totals[mt] = None

        avg  = sub['average']
        grade_lbl, gp_str, g_col = get_grade(avg)
        att  = sub['att_pct']
        att_col = C_SUCCESS if (att or 0) >= 75 else (C_WARNING if (att or 0) >= 60 else C_DANGER)

        row = [
            ph(sub['name'][:28], align=TA_LEFT, color=C_DARK, size=8),
            ph(sub['code'], color=C_DARK, size=8),
        ]
        for mt in all_types:
            val = type_totals.get(mt)
            row.append(ph(f'{val:.0f}' if val is not None else '—', color=C_DARK, size=8))

        row += [
            ph(f"{sub['total_marks']:.0f}" if sub['count_marks'] > 0 else '—', color=C_DARK, size=8),
            ph(f'{avg}' if avg is not None else '—', color=C_DARK, size=8),
            ph(f'{att}%' if att is not None else '—', color=att_col, size=8, bold=True),
            ph(grade_lbl, bold=True, color=g_col, size=8.5),
        ]
        marks_rows.append(row)

    # Grand total row
    grand_type_row = [ph('TOTAL / OVERALL', True, TA_LEFT, C_WHITE, 8.5), ph('—', color=C_WHITE)]
    for mt in all_types:
        vals = [sub['by_type'].get(mt) for sub in data['subjects']]
        grand_type = sum(
            sum(e['marks'] for e in v) for v in vals if v is not None
        )
        grand_type_row.append(ph(f'{grand_type:.0f}', True, color=C_WHITE))
    grand_type_row += [
        ph(f"{sum(s['total_marks'] for s in data['subjects']):.0f}", True, color=C_WHITE),
        ph(f"{overall_avg}" if overall_avg else '—', True, color=C_WHITE),
        ph(f"{ov_att}%" if ov_att else '—', True, color=C_WHITE),
        ph(ov_grade, True, color=C_WHITE),
    ]
    marks_rows.append(grand_type_row)

    marks_table = Table(marks_rows, colWidths=FIXED_COLS, repeatRows=1)
    ts = TableStyle([
        # Header
        ('BACKGROUND', (0,0), (-1,0), C_PRIMARY),
        ('TEXTCOLOR', (0,0), (-1,0), C_WHITE),
        # Grand total
        ('BACKGROUND', (0,-1), (-1,-1), C_DARK),
        ('TEXTCOLOR', (0,-1), (-1,-1), C_WHITE),
        # Alternating rows
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [C_WHITE, C_OFF_WHITE]),
        # Grid
        ('GRID', (0,0), (-1,-1), 0.4, C_BORDER),
        ('LINEABOVE', (0,-1), (-1,-1), 1.0, C_ACCENT),
        # Padding
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        # First col left-align
        ('ALIGN', (0,1), (0,-1), 'LEFT'),
    ])
    marks_table.setStyle(ts)
    story.append(marks_table)

    # ─────────────────────────────────────────────────────────────────────────
    # Section 5 — Detailed Marks Breakdown per subject
    # ─────────────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph('Detailed Marks Breakdown by Subject', SECTION_HEAD))

    for sub in data['subjects']:
        if not sub['by_type']:
            continue

        sub_header = Table(
            [[Paragraph(f'<b>{sub["name"]}</b>', ParagraphStyle('sh', fontName='Helvetica-Bold', fontSize=9.5, textColor=C_WHITE, leading=13)),
              Paragraph(sub['code'], ParagraphStyle('sh2', fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#a5b4fc'), leading=13, alignment=TA_RIGHT))]],
            colWidths=[W*0.7, W*0.3]
        )
        sub_header.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), C_PRIMARY),
            ('TOPPADDING', (0,0), (-1,-1), 7),
            ('BOTTOMPADDING', (0,0), (-1,-1), 7),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))

        detail_rows = [[
            ph('Evaluation Type', True, TA_LEFT, C_WHITE),
            ph('Component Name', True, TA_LEFT, C_WHITE),
            ph('Marks', True, color=C_WHITE),
        ]]

        for mt, entries in sub['by_type'].items():
            for idx, entry in enumerate(entries):
                detail_rows.append([
                    Paragraph(mt if idx == 0 else '', ParagraphStyle('dt', fontName='Helvetica-BoldOblique' if idx==0 else 'Helvetica', fontSize=8.5, textColor=C_ACCENT if idx==0 else C_MUTED, leading=12)),
                    Paragraph(entry['name'], ParagraphStyle('dn', fontName='Helvetica', fontSize=8.5, textColor=C_DARK, leading=12)),
                    Paragraph(f'{entry["marks"]:.1f}', ParagraphStyle('dm', fontName='Helvetica-Bold', fontSize=9, textColor=C_DARK, alignment=TA_CENTER, leading=12)),
                ])

        # Sub-total row
        detail_rows.append([
            ph('Subject Total', True, TA_LEFT, C_DARK, 8.5),
            ph('', color=C_DARK),
            ph(f'{sub["total_marks"]:.1f}', True, color=C_PRIMARY, size=9),
        ])

        detail_table = Table(detail_rows, colWidths=[4.5*cm, W - 4.5*cm - 2.5*cm, 2.5*cm], repeatRows=1)
        detail_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4f46e5')),
            ('BACKGROUND', (0,-1), (-1,-1), C_LIGHT),
            ('ROWBACKGROUNDS', (0,1), (-1,-2), [C_WHITE, C_OFF_WHITE]),
            ('GRID', (0,0), (-1,-1), 0.4, C_BORDER),
            ('LINEABOVE', (0,-1), (-1,-1), 0.8, C_ACCENT),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (2,0), (2,-1), 'CENTER'),
        ]))

        story.append(KeepTogether([sub_header, detail_table, Spacer(1, 0.35*cm)]))

    # ─────────────────────────────────────────────────────────────────────────
    # Section 6 — Attendance Summary Table
    # ─────────────────────────────────────────────────────────────────────────
    story.append(Paragraph('Attendance Summary', SECTION_HEAD))

    att_header = [ph('Subject', True, TA_LEFT, C_WHITE),
                  ph('Code', True, color=C_WHITE),
                  ph('Total Hours', True, color=C_WHITE),
                  ph('Present', True, color=C_WHITE),
                  ph('Absent', True, color=C_WHITE),
                  ph('Percentage', True, color=C_WHITE),
                  ph('Status', True, color=C_WHITE)]
    att_rows = [att_header]

    for sub in data['subjects']:
        att   = sub['att_pct']
        pres  = sub['present']
        tot   = sub['total_hours']
        absent = tot - pres

        if att is None:
            status_txt = '—'
            s_col = C_MUTED
        elif att >= 75:
            status_txt = '✓ Good'
            s_col      = C_SUCCESS
        elif att >= 60:
            status_txt = '⚠ Low'
            s_col      = C_WARNING
        else:
            status_txt = '✗ Poor'
            s_col      = C_DANGER

        hex_sc = s_col.hexval()[2:] if hasattr(s_col, 'hexval') else '000000'
        att_rows.append([
            ph(sub['name'][:28], align=TA_LEFT, color=C_DARK, size=8),
            ph(sub['code'], color=C_DARK, size=8),
            ph(str(tot), color=C_DARK),
            ph(str(pres), color=C_SUCCESS if pres > 0 else C_MUTED),
            ph(str(absent), color=C_DANGER if absent > 0 else C_MUTED),
            ph(f'{att}%' if att is not None else '—', color=s_col if att else C_MUTED, bold=att is not None),
            Paragraph(f'<font name="Helvetica-Bold" size="8" color="#{hex_sc}">{status_txt}</font>',
                      ParagraphStyle('st', alignment=TA_CENTER, leading=12)),
        ])

    # Overall row
    ov_a   = data['overall_att']
    ov_col_att = C_SUCCESS if (ov_a or 0) >= 75 else (C_WARNING if (ov_a or 0) >= 60 else C_DANGER)
    att_rows.append([
        ph('OVERALL', True, TA_LEFT, C_WHITE, 8.5),
        ph('—', color=C_WHITE),
        ph(str(data['total_hours']), True, color=C_WHITE),
        ph(str(data['total_present']), True, color=C_WHITE),
        ph(str(data['total_hours'] - data['total_present']), True, color=C_WHITE),
        ph(f'{ov_a}%' if ov_a else '—', True, color=ov_col_att),
        ph('', color=C_WHITE),
    ])

    att_col_widths = [4.0*cm, 1.4*cm, 1.8*cm, 1.6*cm, 1.5*cm, 1.9*cm, 2.0*cm]
    att_table = Table(att_rows, colWidths=att_col_widths, repeatRows=1)
    att_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), C_PRIMARY),
        ('BACKGROUND', (0,-1), (-1,-1), C_DARK),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [C_WHITE, C_OFF_WHITE]),
        ('GRID', (0,0), (-1,-1), 0.4, C_BORDER),
        ('LINEABOVE', (0,-1), (-1,-1), 1.0, C_ACCENT),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (0,1), (0,-1), 'LEFT'),
        ('ALIGN', (2,0), (-1,-1), 'CENTER'),
    ]))
    story.append(att_table)

    # ─────────────────────────────────────────────────────────────────────────
    # Section 7 — Declaration & Signature block
    # ─────────────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.8*cm))
    story.append(HRFlowable(width=W, color=C_BORDER, thickness=0.5, spaceAfter=8))

    sig_data = [[
        Paragraph(
            'This report is system-generated by <b>EduNexus ERP</b> and reflects data as of the date of generation. '
            'Marks and attendance may be updated by faculty at any time. This document is for informational purposes only.',
            ParagraphStyle('Decl', fontName='Helvetica-Oblique', fontSize=7.5, textColor=C_MUTED, leading=11)
        ),
        Table(
            [[Paragraph('_______________________________', SMALL)],
             [Paragraph('Authorised Signatory', SMALL)],
             [Paragraph('EduNexus Academic Office', SMALL)]],
            colWidths=[5.5*cm]
        )
    ]]
    sig_table = Table(sig_data, colWidths=[W - 6.5*cm, 6.5*cm])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('ALIGN', (1,0), (1,-1), 'CENTER'),
    ]))
    story.append(sig_table)

    # ─────────────────────────────────────────────────────────────────────────
    # Build
    # ─────────────────────────────────────────────────────────────────────────
    doc.build(story)
    return buf.getvalue()


# ── Route ─────────────────────────────────────────────────────────────────────
@report_bp.route('/report', methods=['GET'])
@token_required(allowed_roles=['student'])
def download_report(current_user):
    data, err = _fetch_report_data(current_user['user_id'])
    if err:
        from flask import jsonify
        return jsonify({'message': err}), 404

    try:
        pdf_bytes = build_pdf(data)
    except Exception as e:
        from flask import jsonify
        import traceback
        traceback.print_exc()
        return jsonify({'message': f'PDF generation failed: {str(e)}'}), 500

    name   = data['profile'].get('name', 'student').replace(' ', '_')
    reg    = data['profile'].get('register_number', 'report')
    fname  = f'ReportCard_{reg}_{datetime.datetime.now().strftime("%Y%m%d")}.pdf'

    response = make_response(pdf_bytes)
    response.headers['Content-Type']        = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="{fname}"'
    response.headers['Content-Length']      = len(pdf_bytes)
    response.headers['Cache-Control']       = 'no-cache'
    return response
