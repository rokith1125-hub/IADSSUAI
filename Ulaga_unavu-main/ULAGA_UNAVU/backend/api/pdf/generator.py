"""
PDF generator for ULAGA_UNAVU
"""

import logging
import io
import os
from datetime import datetime
from typing import Dict, List, Optional, BinaryIO

# PDF generation imports
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Cloudinary imports
try:
    import cloudinary
    import cloudinary.uploader
    CLOUDINARY_AVAILABLE = True
except ImportError:
    CLOUDINARY_AVAILABLE = False

try:
    from services.pdf_service import PDFService
except ImportError:
    from services.pdf_service import PDFService

logger = logging.getLogger(__name__)

class PDFGenerator:
    """PDF generation service with reportlab and Cloudinary upload"""
    
    def __init__(self):
        self.pdf_service = PDFService()
        self.cloudinary_configured = self._init_cloudinary()
        self.styles = None
        if REPORTLAB_AVAILABLE:
            self.styles = getSampleStyleSheet()
            self._setup_custom_styles()
    
    def _init_cloudinary(self) -> bool:
        """Initialize Cloudinary configuration"""
        if not CLOUDINARY_AVAILABLE:
            return False
        try:
            cloud_name = (os.getenv('CLOUDINARY_CLOUD_NAME') or '').strip()
            api_key = (os.getenv('CLOUDINARY_API_KEY') or '').strip()
            api_secret = (os.getenv('CLOUDINARY_API_SECRET') or '').strip()
            
            if cloud_name and api_key and api_secret:
                cloudinary.config(
                    cloud_name=cloud_name,
                    api_key=api_key,
                    api_secret=api_secret,
                    secure=True
                )
                return True
        except Exception as e:
            logger.error(f"Cloudinary config error: {str(e)}")
        return False
    
    def _setup_custom_styles(self):
        """Setup custom PDF styles"""
        if not self.styles:
            return
            
        self.styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading1'],
            fontSize=20,
            textColor=colors.HexColor('#1E3A8A'),
            alignment=TA_CENTER,
            spaceAfter=20
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#374151'),
            spaceAfter=12
        ))
    
    def generate_soil_report(self, soil_data: Dict, user_data: Dict) -> bytes:
        """Generate soil analysis report PDF"""
        if not REPORTLAB_AVAILABLE:
            return self.pdf_service.generate_soil_report(soil_data, user_data)
        
        try:
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
            story = []
            
            # Title
            story.append(Paragraph("Soil Analysis Report", self.styles['ReportTitle']))
            story.append(Spacer(1, 20))
            
            # User Info
            story.append(Paragraph("Farmer Details", self.styles['SectionHeader']))
            user_info = [
                ["Name:", user_data.get('name', 'N/A')],
                ["Location:", user_data.get('farm_info', {}).get('district', 'N/A')],
                ["Date:", datetime.now().strftime('%d %B %Y')],
                ["Report ID:", f"SOIL_{datetime.now().strftime('%Y%m%d%H%M%S')}"]
            ]
            user_table = Table(user_info, colWidths=[100, 300])
            user_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F3F4F6')),
            ]))
            story.append(user_table)
            story.append(Spacer(1, 20))
            
            # Soil Results
            story.append(Paragraph("Analysis Results", self.styles['SectionHeader']))
            soil_results = [
                ["Soil Type:", soil_data.get('soil_name', 'N/A')],
                ["Confidence:", f"{soil_data.get('confidence', 0)*100:.1f}%"],
                ["pH Range:", soil_data.get('soil_properties', {}).get('ph_range', 'N/A')],
                ["Fertility:", soil_data.get('soil_properties', {}).get('fertility', 'N/A')],
                ["Water Retention:", soil_data.get('soil_properties', {}).get('water_retention', 'N/A')]
            ]
            soil_table = Table(soil_results, colWidths=[150, 250])
            soil_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            story.append(soil_table)
            story.append(Spacer(1, 20))
            
            # Recommendations
            explanation = soil_data.get('explanation', {})
            if explanation.get('dos'):
                story.append(Paragraph("Recommendations:", self.styles['SectionHeader']))
                for item in explanation['dos'][:5]:
                    story.append(Paragraph(f"• {item}", self.styles['Normal']))
            
            doc.build(story)
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Soil report generation error: {str(e)}")
            return self.pdf_service.generate_soil_report(soil_data, user_data)
    
    def generate_crop_report(self, crop_data: Dict, user_data: Dict) -> bytes:
        """Generate crop recommendation report PDF"""
        if not REPORTLAB_AVAILABLE:
            return self.pdf_service.generate_crop_report(crop_data, user_data)
        
        try:
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
            story = []
            
            # Title
            story.append(Paragraph("Crop Recommendation Report", self.styles['ReportTitle']))
            story.append(Spacer(1, 20))
            
            # User Info
            story.append(Paragraph("Farmer Details", self.styles['SectionHeader']))
            user_info = [
                ["Name:", user_data.get('name', 'N/A')],
                ["Location:", user_data.get('farm_info', {}).get('district', 'N/A')],
                ["Date:", datetime.now().strftime('%d %B %Y')]
            ]
            user_table = Table(user_info, colWidths=[100, 300])
            user_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ]))
            story.append(user_table)
            story.append(Spacer(1, 20))
            
            # Crop Recommendations
            story.append(Paragraph("Recommended Crops", self.styles['SectionHeader']))
            crops = crop_data.get('recommendations', [])
            for i, crop in enumerate(crops[:5], 1):
                story.append(Paragraph(f"{i}. {crop.get('crop_name', 'N/A')} - Match: {crop.get('match_score', 0)*100:.0f}%", self.styles['Normal']))
                if crop.get('reason'):
                    story.append(Paragraph(f"   Reason: {crop.get('reason')}", self.styles['Normal']))
            
            doc.build(story)
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Crop report generation error: {str(e)}")
            return self.pdf_service.generate_crop_report(crop_data, user_data)
    
    def generate_disease_report(self, disease_data: Dict, user_data: Dict) -> bytes:
        """Generate disease detection report PDF"""
        if not REPORTLAB_AVAILABLE:
            return self.pdf_service.generate_disease_report(disease_data, user_data)
        
        try:
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
            story = []
            
            # Title
            story.append(Paragraph("Disease Detection Report", self.styles['ReportTitle']))
            story.append(Spacer(1, 20))
            
            # User Info
            story.append(Paragraph("Farmer Details", self.styles['SectionHeader']))
            user_info = [
                ["Name:", user_data.get('name', 'N/A')],
                ["Location:", user_data.get('farm_info', {}).get('district', 'N/A')],
                ["Date:", datetime.now().strftime('%d %B %Y')]
            ]
            user_table = Table(user_info, colWidths=[100, 300])
            story.append(user_table)
            story.append(Spacer(1, 20))
            
            # Disease Results
            story.append(Paragraph("Detection Results", self.styles['SectionHeader']))
            disease_results = [
                ["Disease:", disease_data.get('disease_name', 'N/A')],
                ["Confidence:", f"{disease_data.get('confidence', 0)*100:.1f}%"],
                ["Severity:", disease_data.get('severity', 'N/A')],
                ["Affected Crop:", disease_data.get('affected_crop', 'N/A')]
            ]
            disease_table = Table(disease_results, colWidths=[150, 250])
            disease_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            story.append(disease_table)
            story.append(Spacer(1, 20))
            
            # Treatment
            treatment = disease_data.get('treatment', {})
            if treatment.get('organic'):
                story.append(Paragraph("Organic Treatment:", self.styles['SectionHeader']))
                for item in treatment['organic'][:5]:
                    story.append(Paragraph(f"• {item}", self.styles['Normal']))
            
            if treatment.get('chemical'):
                story.append(Spacer(1, 10))
                story.append(Paragraph("Chemical Treatment:", self.styles['SectionHeader']))
                for item in treatment['chemical'][:3]:
                    story.append(Paragraph(f"• {item}", self.styles['Normal']))
            
            doc.build(story)
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Disease report generation error: {str(e)}")
            return self.pdf_service.generate_disease_report(disease_data, user_data)
    
    def upload_to_cloudinary(self, pdf_bytes: bytes, folder: str = "ulagau_reports") -> Dict:
        """Upload PDF to Cloudinary"""
        if not self.cloudinary_configured:
            logger.warning("Cloudinary not configured")
            return {"error": "Cloudinary not configured", "success": False}
        
        try:
            # Generate unique filename
            filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Upload to Cloudinary
            result = cloudinary.uploader.upload(
                pdf_bytes,
                folder=folder,
                public_id=filename,
                resource_type="raw",
                format="pdf"
            )
            
            return {
                "success": True,
                "url": result.get('secure_url'),
                "public_id": result.get('public_id'),
                "created_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Cloudinary upload error: {str(e)}")
            return {"error": str(e), "success": False}
    
    def generate_comprehensive_report(self, user_data: Dict, module_data: Dict) -> bytes:
        """Generate comprehensive farming report PDF"""
        return self.pdf_service.generate_comprehensive_report(user_data, module_data)
    
    def generate_pdf_from_html(self, html_content: str) -> bytes:
        """Generate PDF from HTML content"""
        return self.pdf_service.generate_pdf_from_html(html_content)
    
    def delete_from_cloudinary(self, public_id: str) -> bool:
        """Delete PDF from Cloudinary"""
        return self.pdf_service.delete_from_cloudinary(public_id)
