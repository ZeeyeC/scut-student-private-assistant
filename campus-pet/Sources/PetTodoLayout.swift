import AppKit

enum PetTodoLayout {
    enum Side { case left, right }
    static func frame(near characterRect: NSRect, within visibleFrame: NSRect, preferredSide: Side) -> NSRect {
        let safe=visibleFrame.insetBy(dx:12,dy:12), gap:CGFloat=32
        let w=min(328,safe.width),h=min(360,safe.height)
        func clamp(_ n:CGFloat,_ lower:CGFloat,_ upper:CGFloat)->CGFloat { min(max(n,lower),max(lower,upper)) }
        let y=clamp(characterRect.minY+5,safe.minY,safe.maxY-h)
        let left=NSRect(x:characterRect.minX-gap-w,y:y,width:w,height:h)
        let right=NSRect(x:characterRect.maxX+gap,y:y,width:w,height:h)
        let x=clamp(characterRect.midX-w/2,safe.minX,safe.maxX-w)
        let above=NSRect(x:x,y:characterRect.maxY+gap,width:w,height:h)
        let below=NSRect(x:x,y:characterRect.minY-gap-h,width:w,height:h)
        let candidates=preferredSide == .left ? [left,right,above,below] : [right,left,above,below]
        if let frame=candidates.first(where:{safe.contains($0) && !$0.intersects(characterRect)}) { return frame }
        // Constrained displays keep header/footer and scroll the body; never move the pet.
        let spaces=[
            NSRect(x:safe.minX,y:safe.minY,width:max(0,characterRect.minX-gap-safe.minX),height:safe.height),
            NSRect(x:characterRect.maxX+gap,y:safe.minY,width:max(0,safe.maxX-characterRect.maxX-gap),height:safe.height),
            NSRect(x:safe.minX,y:characterRect.maxY+gap,width:safe.width,height:max(0,safe.maxY-characterRect.maxY-gap)),
            NSRect(x:safe.minX,y:safe.minY,width:safe.width,height:max(0,characterRect.minY-gap-safe.minY))]
        let region=spaces.max{min($0.width,w)*min($0.height,h)<min($1.width,w)*min($1.height,h)}!
        return NSRect(x:clamp(x,region.minX,region.maxX-min(w,region.width)),y:clamp(y,region.minY,region.maxY-min(h,region.height)),width:min(w,region.width),height:min(h,region.height))
    }
}
