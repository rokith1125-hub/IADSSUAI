"""
PDF generation endpoints for ULAGA_UNAVU (FastAPI).
"""

import io
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.common.auth import get_current_user
from api.common.responses import error_response
from services.local_storage import db_service
from utils.path_utils import get_dataset_path
from .generator import PDFGenerator

logger = logging.getLogger(__name__)

router = APIRouter()
pdf_generator = PDFGenerator()


class CustomReportRequest(BaseModel):
    content: str
    type: Optional[str] = "custom"
    title: Optional[str] = "Custom Report"


@router.get("/")
def pdf_info():
    """Get PDF module information."""
    return {
        "module": "PDF Generator",
        "endpoints": {
            "soil_report": "/soil-report (POST, auth)",
            "crop_report": "/crop-report (POST, auth)",
            "disease_report": "/disease-report (POST, auth)",
            "comprehensive_report": "/comprehensive-report (POST, auth)",
            "custom_report": "/custom-report (POST, auth)",
            "reports": "/reports (GET, auth)",
            "report_details": "/report/<id> (GET, auth)",
        },
    }


@router.post("/soil-report")
def generate_soil_report(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Generate soil analysis report PDF."""
    try:
        user_id = current_user["user_id"]
        soil_results = db_service.find("soil_results", {"user_id": user_id}, sort=[("created_at", -1)], limit=1)
        soil_result = soil_results[0] if soil_results else None
        if not soil_result:
            return error_response("No soil analysis found", 404)

        user = db_service.find_one("users", {"user_id": user_id})
        if not user:
            return error_response("User not found", 404)

        pdf_bytes = pdf_generator.generate_soil_report(soil_result, user)
        upload_result = pdf_generator.upload_to_cloudinary(pdf_bytes, "soil_reports")
        if upload_result.get("success") and soil_result.get("_id"):
            db_service.update_one(
                "soil_results",
                {"_id": soil_result["_id"]},
                {"$set": {"pdf_url": upload_result.get("url")}},
            )

        filename = f"soil_report_{datetime.now().strftime('%Y%m%d')}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error("Soil report error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/crop-report")
def generate_crop_report(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Generate crop recommendation report PDF."""
    try:
        user_id = current_user["user_id"]
        crop_selections = db_service.find(
            "crop_selections",
            {"user_id": user_id, "is_active": True},
            sort=[("selected_at", -1)],
            limit=1,
        )
        crop_selection = crop_selections[0] if crop_selections else None
        if not crop_selection:
            return error_response("No active crop selection found", 404)

        user = db_service.find_one("users", {"user_id": user_id})
        if not user:
            return error_response("User not found", 404)

        crop_data = _get_crop_details(crop_selection.get("crop_name"))
        crop_pdf_data = {
            "selected_crop": {
                "name": crop_selection.get("crop_name"),
                "image_url": crop_selection.get("image_url", ""),
            },
            "crop_details": crop_data,
            "recommendations": crop_selection.get("recommendations", []),
        }

        pdf_bytes = pdf_generator.generate_crop_report(crop_pdf_data, user)
        upload_result = pdf_generator.upload_to_cloudinary(pdf_bytes, "crop_reports")
        if upload_result.get("success") and crop_selection.get("_id"):
            db_service.update_one(
                "crop_selections",
                {"_id": crop_selection["_id"]},
                {"$set": {"pdf_url": upload_result.get("url")}},
            )

        filename = f"crop_report_{crop_selection.get('crop_name', '').replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error("Crop report error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/disease-report")
def generate_disease_report(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Generate disease detection report PDF."""
    try:
        user_id = current_user["user_id"]
        disease_results = db_service.find("disease_results", {"user_id": user_id}, sort=[("created_at", -1)], limit=1)
        disease_result = disease_results[0] if disease_results else None
        if not disease_result:
            return error_response("No disease detection found", 404)

        user = db_service.find_one("users", {"user_id": user_id})
        if not user:
            return error_response("User not found", 404)

        pdf_bytes = pdf_generator.generate_disease_report(disease_result, user)
        upload_result = pdf_generator.upload_to_cloudinary(pdf_bytes, "disease_reports")
        if upload_result.get("success") and disease_result.get("_id"):
            db_service.update_one(
                "disease_results",
                {"_id": disease_result["_id"]},
                {"$set": {"pdf_url": upload_result.get("url")}},
            )

        filename = f"disease_report_{datetime.now().strftime('%Y%m%d')}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error("Disease report error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/comprehensive-report")
def generate_comprehensive_report(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Generate comprehensive farming report PDF."""
    try:
        user_id = current_user["user_id"]
        user = db_service.find_one("users", {"user_id": user_id})
        if not user:
            return error_response("User not found", 404)

        module_data = _get_all_module_data(user_id)
        pdf_bytes = pdf_generator.generate_comprehensive_report(user, module_data)
        upload_result = pdf_generator.upload_to_cloudinary(pdf_bytes, "comprehensive_reports")

        report_data = {
            "user_id": user_id,
            "report_type": "comprehensive",
            "pdf_url": upload_result.get("url") if upload_result.get("success") else "",
            "generated_at": datetime.utcnow().isoformat(),
            "module_data": list(module_data.keys()),
        }
        db_service.insert_one("pdf_reports", report_data)

        filename = f"farming_report_{datetime.now().strftime('%Y%m%d')}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error("Comprehensive report error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/custom-report")
def generate_custom_report(
    payload: CustomReportRequest = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate custom report from HTML/text content."""
    try:
        user_id = current_user["user_id"]
        data = payload.model_dump()
        pdf_bytes = pdf_generator.generate_pdf_from_html(data["content"])
        upload_result = pdf_generator.upload_to_cloudinary(pdf_bytes, "custom_reports")

        report_data = {
            "user_id": user_id,
            "report_type": data.get("type", "custom"),
            "title": data.get("title", "Custom Report"),
            "pdf_url": upload_result.get("url") if upload_result.get("success") else "",
            "generated_at": datetime.utcnow().isoformat(),
        }
        inserted = db_service.insert_one("pdf_reports", report_data)

        return {
            "success": True,
            "message": "Custom report generated",
            "pdf_url": upload_result.get("url") if upload_result.get("success") else "",
            "report_id": str(getattr(inserted, "inserted_id", "")),
        }
    except Exception as e:
        logger.error("Custom report error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/reports")
def get_user_reports(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get user's generated reports."""
    try:
        user_id = current_user["user_id"]
        reports = db_service.find("pdf_reports", {"user_id": user_id}, sort=[("generated_at", -1)], limit=20)
        for report in reports:
            if "_id" in report:
                report["report_id"] = str(report.pop("_id"))
        return {"success": True, "reports": reports}
    except Exception as e:
        logger.error("Get reports error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/report/{report_id}")
def get_report_details(report_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get details of specific report."""
    try:
        user_id = current_user["user_id"]
        report = db_service.find_one("pdf_reports", {"_id": report_id, "user_id": user_id})
        if not report:
            return error_response("Report not found", 404)
        if "_id" in report:
            report["report_id"] = str(report.pop("_id"))
        return {"success": True, "report": report}
    except Exception as e:
        logger.error("Get report details error: %s", str(e))
        return error_response(str(e), 500)


def _get_crop_details(crop_name: str) -> Dict:
    """Get crop details from dataset."""
    try:
        import json
        import os

        dataset_path = get_dataset_path("crop_data.json")
        if os.path.exists(dataset_path):
            with open(dataset_path, "r", encoding="utf-8") as f:
                crops = json.load(f)
            for crop in crops:
                if crop["crop_name"].lower() == crop_name.lower():
                    return crop
        return {}
    except Exception as e:
        logger.error("Get crop details error: %s", str(e))
        return {}


def _get_all_module_data(user_id: str) -> Dict:
    """Get data from all modules for comprehensive report."""
    module_data = {}
    try:
        collections = {
            "soil": "soil_results",
            "crop": "crop_selections",
            "disease": "disease_results",
            "fertilizer": "fertilizer_schedules",
            "growth": "growth_timelines",
            "market": "market_snapshots",
            "weather": "weather_cache",
        }
        for module, collection_name in collections.items():
            results = db_service.find(collection_name, {"user_id": user_id}, sort=[("created_at", -1)], limit=1)
            if results:
                data = results[0]
                data.pop("_id", None)
                module_data[module] = data
        return module_data
    except Exception as e:
        logger.error("Get all module data error: %s", str(e))
        return module_data
