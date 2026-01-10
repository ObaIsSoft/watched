
# --- DIRECT MESSAGING ---
class MessageRequest(BaseModel):
    recipient_id: int
    content: str

@app.post("/api/inbox/send")
def send_message(req: MessageRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Verify recipient
    recipient = db.query(User).filter(User.id == req.recipient_id).first()
    if not recipient: raise HTTPException(status_code=404, detail="Recipient not found")
    
    msg = InboxMessage(
        sender_id=current_user.id,
        receiver_id=req.recipient_id,
        type='dm',
        message=req.content,
        read=False
    )
    db.add(msg)
    db.commit()
    return {"status": "sent"}

@app.get("/api/inbox")
def get_inbox(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    msgs = db.query(InboxMessage).filter(InboxMessage.receiver_id == current_user.id).order_by(InboxMessage.created_at.desc()).all()
    
    # Enrich with sender info
    result = []
    for m in msgs:
        sender = db.query(User).filter(User.id == m.sender_id).first()
        result.append({
            "id": m.id,
            "sender_name": sender.name if sender else "Unknown",
            "sender_pic": sender.picture if sender else "",
            "message": m.message,
            "type": m.type,
            "content_id": m.content_id,
            "read": m.read,
            "created_at": m.created_at.isoformat()
        })
    return result
