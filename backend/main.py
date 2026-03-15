import os
import cloudinary
import cloudinary.uploader
import cloudinary.api
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware

# Import your database and model configurations
from backend.database import Base, SessionLocal, engine
from backend.models import Project, Comment

# Configure Cloudinary with your credentials
cloudinary.config(
    cloud_name="dwq5t9s6v",  # Your cloud name from screenshot
    api_key=os.environ.get("CLOUDINARY_API_KEY"),  # Set in Render environment
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),  # Set in Render environment
    secure=True
)

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Your Vercel frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Mount Static Folders (only for frontend files - no uploads folder needed)
os.makedirs("frontend", exist_ok=True)
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# 2. Database Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 3. No need for upload folders creation anymore

# 4. Serve index.html at root
@app.get("/", response_class=HTMLResponse)
async def read_index():
    file_path = os.path.join("frontend", "index.html")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>index.html not found in /frontend folder!</h1>")

# 5. UPLOAD TO CLOUDINARY INSTEAD OF LOCAL DISK
@app.post("/upload/project")
async def upload_project(
    title: str = Form(...),
    location: str = Form(...),
    description: str = Form(...),
    section: str = Form(...),  # 'completed' or 'progress'
    db: Session = Depends(get_db),
    file: UploadFile = File(...)
):
    try:
        # Read file content
        file_content = await file.read()
        
        # Create a unique public_id
        timestamp = int(datetime.now().timestamp())
        public_id = f"projects/{section}/{title.replace(' ', '_')}_{timestamp}"
        
        # Upload to Cloudinary
        upload_result = cloudinary.uploader.upload(
            file_content,
            public_id=public_id,
            overwrite=True,
            resource_type="auto",
            folder=f"projects/{section}"  # Organize in folders
        )
        
        # Get the secure URL from Cloudinary
        image_url = upload_result['secure_url']
        
        # Save to database with Cloudinary URL
        new_project = Project(
            title=title,
            location=location,
            description=description,
            section=section,
            image_path=image_url  # Now storing Cloudinary URL, not local path
        )
        
        db.add(new_project)
        db.commit()
        db.refresh(new_project)
        
        return {
            "status": "success", 
            "image_url": image_url,
            "public_id": upload_result['public_id']
        }
        
    except Exception as e:
        print(f"Server Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 6. Fetch Projects by Section
@app.get("/projects/{section}")
async def get_projects(section: str, db: Session = Depends(get_db)):
    projects = db.query(Project).filter(Project.section == section).all()
    # Convert to list of dicts for JSON response
    return [
        {
            "id": p.id,
            "title": p.title,
            "location": p.location,
            "description": p.description,
            "section": p.section,
            "image_path": p.image_path  # This will be Cloudinary URL
        }
        for p in projects
    ]

# 7. Get all projects (for admin)
@app.get("/projects")
async def get_all_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).all()
    return [
        {
            "id": p.id,
            "title": p.title,
            "location": p.location,
            "description": p.description,
            "section": p.section,
            "image_path": p.image_path
        }
        for p in projects
    ]

# 8. Delete project and its image from Cloudinary
@app.delete("/projects/{project_id}")
async def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Extract public_id from Cloudinary URL
    if project.image_path and "cloudinary" in project.image_path:
        try:
            # Get public_id from URL
            public_id = project.image_path.split('/')[-1].split('.')[0]
            folder = "projects/" + project.section
            full_public_id = f"{folder}/{public_id}"
            
            # Delete from Cloudinary
            cloudinary.uploader.destroy(full_public_id)
        except Exception as e:
            print(f"Cloudinary delete error: {e}")
    
    # Delete from database
    db.delete(project)
    db.commit()
    
    return {"status": "success", "message": "Project deleted"}

# 9. Comment Endpoints
@app.post("/comments")
async def add_comment(
    name: str = Form(...),
    email: str = Form(...),
    comment: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        new_comment = Comment(
            name=name,
            email=email,
            comment=comment,
            created_at=datetime.now()
        )
        db.add(new_comment)
        db.commit()
        db.refresh(new_comment)
        return {
            "status": "success",
            "id": new_comment.id,
            "message": "Comment added successfully"
        }
    except Exception as e:
        print(f"Comment error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/comments")
async def get_comments(db: Session = Depends(get_db)):
    comments = db.query(Comment).order_by(Comment.id.desc()).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "comment": c.comment,
            "created_at": c.created_at.isoformat() if c.created_at else None
        }
        for c in comments
    ]

# 10. Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "cloudinary": "configured"
    }

# 11. Optional: Test Cloudinary connection
@app.get("/test-cloudinary")
async def test_cloudinary():
    try:
        # Test API connection
        result = cloudinary.api.ping()
        return {"status": "connected", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}