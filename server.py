from fastapi import FastAPI
from pydantic import BaseModel
from render_pipeline import run_pipeline
import traceback
import threading

app = FastAPI()

class RenderRequest(BaseModel):
    drive_folder_id: str
    num_scenes: int
    image_ext: str = "png"
    callback_url: str
    record_id: str

@app.post("/generate-video")
def generate_video(req: RenderRequest):
    # try:
    #     result = run_pipeline(
    #         drive_folder_id=req.drive_folder_id,
    #         num_scenes=req.num_scenes,
    #         image_ext=req.image_ext
    #     )
    #     return {"status": "success", **result}
    # except Exception as e:
    #    traceback.print_exc()
    #    return {
    #      "status": "error",
    #      "message": str(e),
    #      "traceback": traceback.format_exc()
    #    }
    threading.Thread(
        target=run_pipeline,
        kwargs={
        "drive_folder_id": req.drive_folder_id,
        "num_scenes": req.num_scenes,
        "image_ext": req.image_ext,
        "callback_url": req.callback_url,
        "record_id": req.record_id,
         },
        daemon=True
    ).start()

    return {
        "status": "started"
    }

@app.get("/")
def health():
    return {"status": "ok"}