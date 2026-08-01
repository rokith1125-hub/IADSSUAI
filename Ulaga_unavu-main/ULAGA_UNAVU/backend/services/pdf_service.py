"""
PDF generation and Cloudinary upload service
"""

import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, BinaryIO
import cloudinary
import cloudinary.uploader
import cloudinary.api
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import io
import tempfile

logger = logging.getLogger(__name__)

class PDFService:
    """Service for PDF generation and Cloudinary upload"""
    
    def __init__(self):
        self.cloudinary_config = self._init_cloudinary()
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _init_cloudinary(self) -> bool:
        """Initialize Cloudinary configuration"""
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
                logger.info("Cloudinary configured successfully")
                return True
            else:
                logger.warning("Cloudinary credentials not configured")
                return False
                
        except Exception as e:
            logger.error(f"Cloudinary initialization error: {str(e)}")
            return False
    
    def _setup_custom_styles(self):
        """Setup custom PDF styles"""
        # Title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1E3A8A'),
            alignment=TA_CENTER,
            spaceAfter=30
        ))
        
        # Subtitle style
        self.styles.add(ParagraphStyle(
            name='CustomSubtitle',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#374151'),
            alignment=TA_LEFT,
            spaceAfter=20
        ))
        
        # Normal style
        self.styles.add(ParagraphStyle(
            name='CustomNormal',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#4B5563'),
            alignment=TA_LEFT,
            spaceAfter=10
        ))
        
        # Highlight style
        self.styles.add(ParagraphStyle(
            name='CustomHighlight',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#059669'),
            backColor=colors.HexColor('#D1FAE5'),
            alignment=TA_LEFT,
            spaceAfter=10
        ))
        
        # Warning style
        self.styles.add(ParagraphStyle(
            name='CustomWarning',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#DC2626'),
            backColor=colors.HexColor('#FEE2E2'),
            alignment=TA_LEFT,
            spaceAfter=10
        ))
    
    def generate_soil_report(self, soil_data: Dict, user_data: Dict) -> bytes:
        """Generate soil analysis report PDF"""
        try:
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=18
            )
            
            story = []
            
            # Title
            story.append(Paragraph("Soil Analysis Report", self.styles['CustomTitle']))
            story.append(Spacer(1, 20))
            
            # User Information
            story.append(Paragraph("Farmer Details", self.styles['CustomSubtitle']))
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
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#4B5563')),
            ]))
            story.append(user_table)
            story.append(Spacer(1, 30))
            
            # Soil Analysis Results
            story.append(Paragraph("Analysis Results", self.styles['CustomSubtitle']))
            
            soil_results = [
                ["Soil Type:", soil_data.get('soil_name', 'N/A')],
                ["Confidence:", f"{soil_data.get('confidence', 0)*100:.1f}%"],
                ["Analysis Method:", soil_data.get('analysis_method', 'N/A')],
                ["", ""]
            ]
            
            # Soil Properties
            properties = soil_data.get('soil_properties', {})
            soil_results.extend([
                ["Hardness:", properties.get('hardness', 'N/A')],
                ["Fertility:", properties.get('fertility', 'N/A')],
                ["Water Retention:", properties.get('water_retention', 'N/A')],
                ["Drainage:", properties.get('drainage', 'N/A')],
                ["pH Range:", properties.get('ph_range', 'N/A')]
            ])
            
            soil_table = Table(soil_results, colWidths=[150, 250])
            soil_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F3F4F6')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#4B5563')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            story.append(soil_table)
            story.append(Spacer(1, 30))
            
            # Explanation
            explanation = soil_data.get('explanation', {})
            if explanation.get('summary'):
                story.append(Paragraph("Soil Summary", self.styles['CustomSubtitle']))
                story.append(Paragraph(explanation['summary'], self.styles['CustomNormal']))
                story.append(Spacer(1, 20))
            
            # Do's and Don'ts
            if explanation.get('dos') or explanation.get('donts'):
                story.append(Paragraph("Recommendations", self.styles['CustomSubtitle']))
                
                if explanation.get('dos'):
                    story.append(Paragraph("<b>Do's:</b>", self.styles['CustomNormal']))
                    for do_item in explanation['dos'][:5]:
                        story.append(Paragraph(f"• {do_item}", self.styles['CustomNormal']))
                    story.append(Spacer(1, 10))
                
                if explanation.get('donts'):
                    story.append(Paragraph("<b>Don'ts:</b>", self.styles['CustomNormal']))
                    for dont_item in explanation['donts'][:5]:
                        story.append(Paragraph(f"• {dont_item}", self.styles['CustomNormal']))
            
            story.append(Spacer(1, 30))
            
            # Suitable Crops
            suitable_crops = properties.get('suitable_crops', [])
            if suitable_crops:
                story.append(Paragraph("Recommended Crops", self.styles['CustomSubtitle']))
                crops_text = ", ".join(suitable_crops[:10])
                story.append(Paragraph(crops_text, self.styles['CustomNormal']))
            
            # Footer
            story.append(Spacer(1, 40))
            story.append(Paragraph("Generated by ULAGA_UNAVU Agriculture AI Platform", 
                                 self.styles['CustomNormal']))
            story.append(Paragraph(f"Report generated on: {datetime.now().strftime('%d %B %Y, %I:%M %p')}", 
                                 self.styles['CustomNormal']))
            
            # Build PDF
            doc.build(story)
            buffer.seek(0)
            
            logger.info(f"Soil report generated for user {user_data.get('user_id')}")
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Error generating soil report: {str(e)}")
            raise
    
    def generate_crop_report(self, crop_data: Dict, user_data: Dict) -> bytes:
        """Generate crop recommendation report PDF"""
        try:
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=18
            )
            
            story = []
            
            # Title
            story.append(Paragraph("Crop Recommendation Report", self.styles['CustomTitle']))
            story.append(Spacer(1, 20))
            
            # User Information
            story.append(Paragraph("Farmer Details", self.styles['CustomSubtitle']))
            user_info = [
                ["Name:", user_data.get('name', 'N/A')],
                ["Location:", user_data.get('farm_info', {}).get('district', 'N/A')],
                ["Soil Type:", user_data.get('current_soil', 'N/A')],
                ["Date:", datetime.now().strftime('%d %B %Y')],
                ["Report ID:", f"CROP_{datetime.now().strftime('%Y%m%d%H%M%S')}"]
            ]
            user_table = Table(user_info, colWidths=[100, 300])
            user_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F3F4F6')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#4B5563')),
            ]))
            story.append(user_table)
            story.append(Spacer(1, 30))
            
            # Selected Crop
            story.append(Paragraph("Selected Crop", self.styles['CustomSubtitle']))
            
            selected_crop = [
                ["Crop Name:", crop_data.get('selected_crop', {}).get('name', 'N/A')],
                ["Scientific Name:", crop_data.get('crop_details', {}).get('scientific_name', 'N/A')],
                ["Tamil Name:", crop_data.get('crop_details', {}).get('tamil_name', 'N/A')],
                ["", ""]
            ]
            
            crop_table = Table(selected_crop, colWidths=[150, 250])
            crop_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F3F4F6')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#4B5563')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            story.append(crop_table)
            story.append(Spacer(1, 20))
            
            # Crop Details
            crop_details = crop_data.get('crop_details', {})
            if crop_details:
                story.append(Paragraph("Crop Specifications", self.styles['CustomSubtitle']))
                
                details_data = [
                    ["Growing Season:", ", ".join(crop_details.get('growing_season', []))],
                    ["Season Months:", crop_details.get('season_months', 'N/A')],
                    ["Water Requirement:", crop_details.get('water_requirement', 'N/A')],
                    ["Growth Days:", str(crop_details.get('growth_days', 'N/A'))],
                    ["Temperature Range:", crop_details.get('temperature_range', 'N/A')],
                    ["Rainfall Needed:", crop_details.get('rainfall_needed', 'N/A')],
                    ["Yield per Acre:", crop_details.get('yield_per_acre', 'N/A')],
                    ["Risk Level:", crop_details.get('risk_level', 'N/A')]
                ]
                
                details_table = Table(details_data, colWidths=[150, 250])
                details_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F3F4F6')),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#4B5563')),
                ]))
                story.append(details_table)
            
            story.append(Spacer(1, 30))
            
            # Growth Stages
            stages = crop_details.get('stages', [])
            if stages:
                story.append(Paragraph("Growth Stages Timeline", self.styles['CustomSubtitle']))
                
                stage_data = [["Stage", "Duration (Days)", "Key Activities"]]
                for stage in stages[:6]:  # Limit to 6 stages
                    activities = stage.get('critical_actions', [])
                    activities_text = ", ".join(activities[:2]) if activities else "Normal care"
                    stage_data.append([
                        stage.get('stage', 'N/A'),
                        str(stage.get('duration_days', 'N/A')),
                        activities_text
                    ])
                
                stage_table = Table(stage_data, colWidths=[100, 80, 220])
                stage_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F9FAFB')),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ]))
                story.append(stage_table)
            
            story.append(Spacer(1, 30))
            
            # Recommendations
            recommendations = crop_data.get('recommendations', [])
            if recommendations:
                story.append(Paragraph("Farming Recommendations", self.styles['CustomSubtitle']))
                
                for rec in recommendations[:5]:
                    style = self.styles['CustomNormal']
                    if rec.get('priority') == 'High':
                        style = self.styles['CustomWarning']
                    elif rec.get('priority') == 'Medium':
                        style = self.styles['CustomHighlight']
                    
                    rec_text = f"<b>{rec.get('type', 'Recommendation')}:</b> {rec.get('action', '')}"
                    story.append(Paragraph(rec_text, style))
            
            # Footer
            story.append(Spacer(1, 40))
            story.append(Paragraph("Generated by ULAGA_UNAVU Agriculture AI Platform", 
                                 self.styles['CustomNormal']))
            story.append(Paragraph(f"Report generated on: {datetime.now().strftime('%d %B %Y, %I:%M %p')}", 
                                 self.styles['CustomNormal']))
            
            # Build PDF
            doc.build(story)
            buffer.seek(0)
            
            logger.info(f"Crop report generated for user {user_data.get('user_id')}")
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Error generating crop report: {str(e)}")
            raise
    
    def generate_disease_report(self, disease_data: Dict, user_data: Dict) -> bytes:
        """Generate disease detection report PDF"""
        try:
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=18
            )
            
            story = []
            
            # Title with severity indicator
            severity = disease_data.get('severity_level', 'Medium')
            severity_color = {
                'High': colors.HexColor('#DC2626'),
                'Medium': colors.HexColor('#F59E0B'),
                'Low': colors.HexColor('#10B981')
            }.get(severity, colors.black)
            
            title_style = ParagraphStyle(
                name='DiseaseTitle',
                parent=self.styles['Heading1'],
                fontSize=24,
                textColor=severity_color,
                alignment=TA_CENTER,
                spaceAfter=20
            )
            
            story.append(Paragraph("Plant Disease Detection Report", title_style))
            story.append(Spacer(1, 10))
            
            # Severity badge
            severity_text = f"Severity: {severity}"
            severity_style = ParagraphStyle(
                name='SeverityBadge',
                parent=self.styles['Normal'],
                fontSize=12,
                textColor=colors.white,
                backColor=severity_color,
                alignment=TA_CENTER,
                leftPadding=20,
                rightPadding=20,
                spaceAfter=30
            )
            story.append(Paragraph(severity_text, severity_style))
            story.append(Spacer(1, 20))
            
            # User Information
            story.append(Paragraph("Detection Details", self.styles['CustomSubtitle']))
            user_info = [
                ["Farmer Name:", user_data.get('name', 'N/A')],
                ["Crop:", disease_data.get('affected_crop', 'N/A')],
                ["Detection Date:", datetime.now().strftime('%d %B %Y')],
                ["Confidence:", f"{disease_data.get('confidence', 0)*100:.1f}%"],
                ["Report ID:", f"DISEASE_{datetime.now().strftime('%Y%m%d%H%M%S')}"]
            ]
            user_table = Table(user_info, colWidths=[120, 280])
            user_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F3F4F6')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#4B5563')),
            ]))
            story.append(user_table)
            story.append(Spacer(1, 30))
            
            # Disease Information
            story.append(Paragraph("Disease Information", self.styles['CustomSubtitle']))
            
            disease_info = [
                ["Disease Name:", disease_data.get('disease_name', 'N/A')],
                ["Tamil Name:", disease_data.get('tamil_name', 'N/A')],
                ["Scientific Name:", disease_data.get('scientific_name', 'N/A')],
                ["Spread Speed:", disease_data.get('spread_speed', 'N/A')],
                ["Contagious:", "Yes" if disease_data.get('contagious') else "No"]
            ]
            
            disease_table = Table(disease_info, colWidths=[150, 250])
            disease_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F3F4F6')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#4B5563')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            story.append(disease_table)
            story.append(Spacer(1, 20))
            
            # Symptoms
            symptoms = disease_data.get('symptoms', [])
            if symptoms:
                story.append(Paragraph("Symptoms", self.styles['CustomSubtitle']))
                for symptom in symptoms[:5]:
                    story.append(Paragraph(f"• {symptom}", self.styles['CustomNormal']))
                story.append(Spacer(1, 20))
            
            # Causes
            causes = disease_data.get('causes', [])
            if causes:
                story.append(Paragraph("Causes", self.styles['CustomSubtitle']))
                for cause in causes[:5]:
                    story.append(Paragraph(f"• {cause}", self.styles['CustomNormal']))
                story.append(Spacer(1, 20))
            
            # Treatment
            treatment = disease_data.get('treatment', {})
            if treatment:
                story.append(Paragraph("Treatment & Prevention", self.styles['CustomSubtitle']))
                
                # Organic Treatment
                organic = treatment.get('organic', [])
                if organic:
                    story.append(Paragraph("<b>Organic Control Methods:</b>", self.styles['CustomNormal']))
                    for method in organic[:3]:
                        story.append(Paragraph(f"• {method}", self.styles['CustomNormal']))
                    story.append(Spacer(1, 10))
                
                # Chemical Treatment
                chemical = treatment.get('chemical', [])
                if chemical:
                    story.append(Paragraph("<b>Chemical Control Methods:</b>", self.styles['CustomWarning']))
                    story.append(Paragraph("<i>Warning: Use chemicals with caution. Follow safety guidelines.</i>", 
                                         self.styles['CustomNormal']))
                    for method in chemical[:3]:
                        story.append(Paragraph(f"• {method}", self.styles['CustomNormal']))
                    story.append(Spacer(1, 10))
                
                # Prevention
                prevention = treatment.get('prevention', [])
                if prevention:
                    story.append(Paragraph("<b>Prevention Methods:</b>", self.styles['CustomNormal']))
                    for method in prevention[:3]:
                        story.append(Paragraph(f"• {method}", self.styles['CustomNormal']))
            
            story.append(Spacer(1, 30))
            
            # Weather Considerations
            weather_warning = disease_data.get('weather_warning', '')
            if weather_warning:
                story.append(Paragraph("Weather Considerations", self.styles['CustomSubtitle']))
                story.append(Paragraph(weather_warning, self.styles['CustomWarning']))
            
            # Footer with safety note
            story.append(Spacer(1, 40))
            story.append(Paragraph("<b>Important Note:</b> For severe infections, consult local agriculture officer.", 
                                 self.styles['CustomWarning']))
            story.append(Spacer(1, 10))
            story.append(Paragraph("Generated by ULAGA_UNAVU Agriculture AI Platform", 
                                 self.styles['CustomNormal']))
            story.append(Paragraph(f"Report generated on: {datetime.now().strftime('%d %B %Y, %I:%M %p')}", 
                                 self.styles['CustomNormal']))
            
            # Build PDF
            doc.build(story)
            buffer.seek(0)
            
            logger.info(f"Disease report generated for user {user_data.get('user_id')}")
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Error generating disease report: {str(e)}")
            raise
    
    def generate_comprehensive_report(self, user_data: Dict, module_data: Dict) -> bytes:
        """Generate comprehensive farming report"""
        try:
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=18
            )
            
            story = []
            
            # Title
            story.append(Paragraph("Comprehensive Farming Report", self.styles['CustomTitle']))
            story.append(Spacer(1, 20))
            
            # Farm Summary
            story.append(Paragraph("Farm Summary", self.styles['CustomSubtitle']))
            
            summary_data = [
                ["Farmer:", user_data.get('name', 'N/A')],
                ["Farm Location:", user_data.get('farm_info', {}).get('district', 'N/A')],
                ["Farm Size:", user_data.get('farm_info', {}).get('farm_size', 'N/A')],
                ["Report Period:", f"{datetime.now().strftime('%B %Y')}"],
                ["Report ID:", f"COMP_{datetime.now().strftime('%Y%m%d%H%M%S')}"]
            ]
            
            summary_table = Table(summary_data, colWidths=[120, 280])
            summary_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F3F4F6')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#4B5563')),
            ]))
            story.append(summary_table)
            story.append(Spacer(1, 30))
            
            # Module-wise Summary
            modules = ['soil', 'crop', 'disease', 'fertilizer', 'growth', 'market', 'weather']
            
            for module in modules:
                if module in module_data and module_data[module]:
                    module_title = module.capitalize() + " Analysis"
                    story.append(Paragraph(module_title, self.styles['CustomSubtitle']))
                    
                    module_info = module_data[module]
                    summary = self._get_module_summary(module, module_info)
                    
                    story.append(Paragraph(summary, self.styles['CustomNormal']))
                    story.append(Spacer(1, 20))
            
            # Recommendations
            story.append(Paragraph("Overall Recommendations", self.styles['CustomSubtitle']))
            
            recommendations = [
                "Monitor soil moisture regularly",
                "Follow fertilizer schedule strictly",
                "Check weather forecast daily",
                "Inspect crops for diseases weekly",
                "Consult market prices before selling"
            ]
            
            for rec in recommendations:
                story.append(Paragraph(f"• {rec}", self.styles['CustomNormal']))
            
            story.append(Spacer(1, 30))
            
            # Financial Summary (if available)
            if 'market' in module_data:
                market_data = module_data['market']
                if isinstance(market_data, dict) and 'expected_value' in market_data:
                    story.append(Paragraph("Financial Outlook", self.styles['CustomSubtitle']))
                    
                    financials = market_data['expected_value']
                    if isinstance(financials, dict):
                        fin_data = [
                            ["Expected Revenue:", f"₹{financials.get('sell_now_mandi', 0):,.2f}"],
                            ["Best Option:", financials.get('best_option', 'MANDI')],
                            ["Recommendation:", market_data.get('recommended_action', 'Consult expert')]
                        ]
                        
                        fin_table = Table(fin_data, colWidths=[150, 250])
                        fin_table.setStyle(TableStyle([
                            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                            ('FONTSIZE', (0, 0), (-1, -1), 10),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F3F4F6')),
                            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#4B5563')),
                        ]))
                        story.append(fin_table)
            
            # Footer
            story.append(Spacer(1, 40))
            story.append(Paragraph("Generated by ULAGA_UNAVU Agriculture AI Platform", 
                                 self.styles['CustomNormal']))
            story.append(Paragraph("This report is for informational purposes only.", 
                                 self.styles['CustomNormal']))
            story.append(Paragraph(f"Generated on: {datetime.now().strftime('%d %B %Y, %I:%M %p')}", 
                                 self.styles['CustomNormal']))
            
            # Build PDF
            doc.build(story)
            buffer.seek(0)
            
            logger.info(f"Comprehensive report generated for user {user_data.get('user_id')}")
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Error generating comprehensive report: {str(e)}")
            raise
    
    def _get_module_summary(self, module: str, data: Dict) -> str:
        """Get summary text for module"""
        if module == 'soil':
            return f"Soil Type: {data.get('soil_name', 'N/A')}, Fertility: {data.get('soil_properties', {}).get('fertility', 'N/A')}"
        elif module == 'crop':
            return f"Crop: {data.get('selected_crop', {}).get('name', 'N/A')}, Stage: {data.get('current_stage', 'N/A')}"
        elif module == 'disease':
            return f"Disease: {data.get('disease_name', 'None detected')}, Severity: {data.get('severity_level', 'N/A')}"
        elif module == 'fertilizer':
            return f"Next Application: {data.get('next_fertilizer', 'N/A')} in {data.get('days_until_next', 'N/A')} days"
        elif module == 'growth':
            return f"Progress: {data.get('progress_percent', 0)}%, Days Remaining: {data.get('days_remaining', 'N/A')}"
        elif module == 'market':
            return f"Decision: {data.get('decision', 'N/A')}, Price: ₹{data.get('prices', {}).get('mandi', 'N/A')}/quintal"
        elif module == 'weather':
            return f"Condition: {data.get('current', {}).get('condition', 'N/A')}, Temp: {data.get('current', {}).get('temperature', 'N/A')}°C"
        else:
            return "Data available"
    
    def upload_to_cloudinary(self, pdf_bytes: bytes, folder: str = "ulagau_reports") -> Dict:
        """Upload PDF to Cloudinary and return URL"""
        if not self.cloudinary_config:
            logger.warning("Cloudinary not configured, saving locally")
            return self._save_locally(pdf_bytes)
        
        try:
            # Upload to Cloudinary
            upload_result = cloudinary.uploader.upload(
                pdf_bytes,
                folder=folder,
                resource_type="raw",
                public_id=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                format="pdf"
            )
            
            logger.info(f"PDF uploaded to Cloudinary: {upload_result.get('secure_url')}")
            
            return {
                "success": True,
                "url": upload_result.get('secure_url'),
                "public_id": upload_result.get('public_id'),
                "format": upload_result.get('format'),
                "bytes": upload_result.get('bytes'),
                "uploaded_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Cloudinary upload error: {str(e)}")
            return self._save_locally(pdf_bytes)
    
    def _save_locally(self, pdf_bytes: bytes) -> Dict:
        """Save PDF locally when Cloudinary fails"""
        try:
            # Create reports directory
            reports_dir = "reports"
            os.makedirs(reports_dir, exist_ok=True)
            
            # Save file
            filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            filepath = os.path.join(reports_dir, filename)
            
            with open(filepath, 'wb') as f:
                f.write(pdf_bytes)
            
            # For development, return local path
            # In production, you might want to serve this via a static route
            local_url = f"/reports/{filename}"
            
            return {
                "success": True,
                "url": local_url,
                "filepath": filepath,
                "filename": filename,
                "note": "Saved locally (Cloudinary not configured)",
                "uploaded_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Local save error: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "uploaded_at": datetime.now().isoformat()
            }
    
    def delete_from_cloudinary(self, public_id: str) -> bool:
        """Delete file from Cloudinary"""
        if not self.cloudinary_config:
            return False
        
        try:
            result = cloudinary.uploader.destroy(public_id, resource_type="raw")
            return result.get('result') == 'ok'
        except Exception as e:
            logger.error(f"Cloudinary delete error: {str(e)}")
            return False
    
    def generate_pdf_from_html(self, html_content: str) -> bytes:
        """Generate PDF from HTML content (simplified)"""
        try:
            # For simplicity, using a basic PDF generation
            # In production, consider using weasyprint or other HTML-to-PDF libraries
            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=A4)
            
            # Simple text rendering
            c.setFont("Helvetica", 12)
            c.drawString(100, 750, "Report Generated from HTML")
            c.drawString(100, 730, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            
            # Add HTML content as text (simplified)
            lines = html_content.split('\n')
            y_position = 700
            for line in lines[:20]:  # Limit lines
                if y_position < 50:
                    c.showPage()
                    y_position = 750
                    c.setFont("Helvetica", 10)
                
                c.drawString(50, y_position, line[:80])  # Limit line length
                y_position -= 15
            
            c.save()
            buffer.seek(0)
            
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"HTML to PDF error: {str(e)}")
            raise
