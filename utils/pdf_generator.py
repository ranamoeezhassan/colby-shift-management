from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from io import BytesIO
from datetime import datetime

def generate_validation_pdf(violations, total_violations):
    """
    Generate a PDF report for validation violations.
    
    Args:
        violations (list): List of violation strings.
        total_violations (int): Total count of violations.
        
    Returns:
        BytesIO: Buffer containing the PDF data.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = styles['Heading1']
    story.append(Paragraph("Validation Report", title_style))
    story.append(Spacer(1, 12))

    # Date
    date_style = styles['Normal']
    story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", date_style))
    story.append(Spacer(1, 12))

    # Summary
    summary_style = styles['Heading2']
    story.append(Paragraph("Summary", summary_style))
    story.append(Paragraph(f"Total Violations Found: {total_violations}", styles['Normal']))
    story.append(Spacer(1, 12))

    # Violations List
    if violations:
        story.append(Paragraph("Detailed Violations:", styles['Heading2']))
        story.append(Spacer(1, 6))
        
        # Create a table for violations
        data = [['#', 'Violation Description']]
        for i, violation in enumerate(violations, 1):
            data.append([str(i), violation])
            
        table = Table(data, colWidths=[30, 400])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("No violations found. System is compliant.", styles['Normal']))

    doc.build(story)
    buffer.seek(0)
    return buffer
