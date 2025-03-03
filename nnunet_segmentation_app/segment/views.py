import os
import time
import requests
import threading
import dicom2nifti
import subprocess
import pydicom
from django.conf import settings
from django.core.mail import send_mail
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.contrib import messages
from werkzeug.utils import secure_filename
from .models import Feedback

FLASK_BACKEND_URL = "https://5c21-34-87-180-203.ngrok-free.app"

UPLOAD_DIR = os.path.join(settings.BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# scheduled deletion
uploaded_file_paths = {}
converted_files = [] 

def is_dicom(file_path):
    
    if check_if_dicom(file_path):
        nifti_file = convert_dicom_to_nifti(file_path, f"{file_path}.nii")
        if nifti_file:
            file_path = nifti_file

    # Modify the filename for display without a separate function
    base_name = os.path.basename(file_path)
    name, ext = os.path.splitext(base_name)

    # Handle .nii files with an additional .gz extension
    if ext == ".gz" and name.endswith(".nii"):
        name, _ = os.path.splitext(name)
        ext = ".nii.gz"
    else:
        ext = ".nii.gz"

    if not name.endswith("_0000"):
        name += "_0000"

    converted_files.append(f"{name}{ext}")

def check_if_dicom(file_path):
    try:
        import pydicom
        pydicom.dcmread(file_path)
        return True
    except Exception:
        return False



# Utility Function to Convert DICOM to NIfTI
def convert_dicom_to_nifti(dicom_path, output_path):
    """Convert a DICOM file to NIfTI format."""
    try:
        dicom2nifti.convert_directory(dicom_path, os.path.dirname(output_path))
        nifti_file = os.path.join(
            os.path.dirname(output_path),
            os.path.basename(dicom_path).replace(".dcm", ".nii"),
        )
        return nifti_file
    except Exception as e:
        print(f"Error converting DICOM to NIfTI: {e}")
        return None

# Scheduled File Deletion
def schedule_file_deletion(file_path, delay=600):  # 10 minutes
    """Delete the file after a set delay."""
    time.sleep(delay)
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"🗑️ Deleted expired file: {file_path}")

#my Home Page
def home(request):
    return render(request, "home.html")

# Fixed Upload Function
@csrf_exempt
def upload_files(request):
    """Handle file uploads and conversion to NIfTI."""
    if request.method == "POST":
        files = request.FILES.getlist("files")  # ✅ Use request.FILES
        uploaded_files = []
        converted_files = []

        for uploaded_file in files:
            file_path = default_storage.save(uploaded_file.name, uploaded_file)  # ✅ Using the default_storage here

            uploaded_files.append(file_path)

            # Track for deletion after 10 minutes
            uploaded_file_paths[file_path] = threading.Thread(target=schedule_file_deletion, args=(file_path,))
            uploaded_file_paths[file_path].start()

            # Check if it's a DICOM file and convert to NIfTI #dummy -> real in backend gpu comp
            if is_dicom(file_path):
                nifti_file = convert_dicom_to_nifti(file_path, f"{file_path}.nii")
                if nifti_file:
                    converted_files.append(nifti_file)
            else:
                converted_files.append(file_path)

        # Process converted filenames before returning
        for i in range(len(converted_files)):
            base_name = os.path.basename(converted_files[i])
            name, ext = os.path.splitext(base_name)

            # Handle .nii.gz correctly
            if ext == ".gz" and name.endswith(".nii"):
                name, _ = os.path.splitext(name)
                ext = ".nii.gz"
            else:
                ext = ".nii.gz"  # Convert .dcm and .nii to .nii.gz

            # Ensure _0000 suffix
            if not name.endswith("_0000"):
                name += "_0000"

            # Update the file in the list
            converted_files[i] = f"{name}{ext}"

        return JsonResponse({"uploaded": uploaded_files, "converted": converted_files})

    
    return JsonResponse({"error": "Invalid request method."}, status=405)

@csrf_exempt
def segment_files(request):
    """Segment NIfTI files using the Flask backend."""
    print("📩 segment_files endpoint triggered")

    if request.method == "POST":
        try:
            files = request.FILES.getlist("nifti_files")
            print(f"📂 Extracted files list: {files}")

            if not files:
                return JsonResponse({"error": "No files uploaded"}, status=400)

            # List to store segmented file names
            segmented_file_names = []

            # Send each file to the Flask backend for processing
            for file in files:
                print(f"🔄 Sending file {file.name} to Flask backend...")

                response = requests.post(
                    f"{FLASK_BACKEND_URL}/predict",
                    files={"files": (file.name, file, file.content_type)}
                )

                # Parse the Flask backend response
                response_data = response.json()
                if response_data.get("status") == "completed":
                    segmented_files = response_data.get("segmented_files", [])
                    segmented_file_names.extend([f["name"] for f in segmented_files])
                else:
                    return JsonResponse({"error": response_data.get("message", "Unknown error")}, status=400)

            # Send segmented file names to Flask to create the zip
            print(f"🔄 Requesting Flask backend to create zip for files: {segmented_file_names}")
            zip_response = requests.post(
                f"{FLASK_BACKEND_URL}/download-all",
                json={"file_names": segmented_file_names}
            )

            if zip_response.status_code == 200:
                zip_data = zip_response.json()
                zip_url = zip_data.get("download_url")
                if zip_url:
                    return JsonResponse({
                        "segmented_files": {"url": zip_url},
                        "status": "completed",
                        "message": f"Processed and zipped {len(segmented_file_names)} files successfully."
                    })
                else:
                    return JsonResponse({"error": "Failed to generate download URL for zip file."}, status=500)
            else:
                return JsonResponse({"error": "Failed to create zip file on backend."}, status=500)

        except Exception as e:
            print(f"❌ Error: {e}")
            return JsonResponse({"error": "Internal server error"}, status=500)

    return JsonResponse({"error": "Invalid request method."}, status=405)

# Newest Feedback Function -> working correctly
@csrf_exempt
def submit_feedback(request):
    """Handle feedback submission."""
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        rating = request.POST.get("rating")
        feedback_text = request.POST.get("feedback")

        Feedback.objects.create(
            name=name,
            email=email,
            rating=rating,
            feedback_text=feedback_text,
        )

        try:
            send_mail(
                subject="New Feedback Submission",
                message=f"Name: {name}\nEmail: {email}\nRating: {rating}\nFeedback: {feedback_text}",
                from_email="navamimurali1@gmail.com",
                recipient_list=["navamimurali1@gmail.com", "tranceit.ae@gmail.com"],
                fail_silently=False,
            )
            messages.success(request, "Feedback submitted successfully!")
        except Exception as e:
            print(f"Error sending email: {e}")
            messages.error(request, "Failed to send feedback. Please try again.")
            return redirect("home")
    return redirect("home")
