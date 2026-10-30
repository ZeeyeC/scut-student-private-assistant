import AppKit

@MainActor
final class PetPlayback {
    let pack: PetAssetPack
    private(set) var mood: PetMood = .starting
    private(set) var reminder = false
    private var action: PetManualAction?
    private var stateElapsed: TimeInterval = 0
    private var actionElapsed: TimeInterval = 0
    var visible = true { didSet { if !visible { stopAction() } } }
    var reducedMotion = false { didSet { if reducedMotion { stopAction(); stateElapsed = 0 } } }
    var activeActionID: String? { action?.id }
    var activeActionTitle: String? { action?.title }
    init(pack: PetAssetPack) { self.pack = pack }

    private var segment: (clip: PetClipSpec, elapsed: TimeInterval) {
        guard let action else { return (pack.clip(for: mood), stateElapsed) }
        var elapsed = actionElapsed
        for (index, name) in action.clips.enumerated() {
            let clip = pack.clips[name]!
            let duration = action.holdMilliseconds.map { Double($0) / 1000 } ?? clip.duration
            if elapsed < duration || index == action.clips.count - 1 { return (clip, elapsed) }
            elapsed -= duration
        }
        return (pack.defaultClip, 0)
    }
    var currentClip: PetClipSpec { segment.clip }
    var frameIndex: Int { let current = segment; return current.clip.frameIndex(at: current.elapsed) }

    func update(mood: PetMood, reminder: Bool) {
        if self.mood != mood { stateElapsed = 0 }
        self.mood = mood; self.reminder = reminder
        if mood != .idle || reminder { stopAction() }
    }
    @discardableResult
    func play(_ id: String) -> Bool {
        guard mood == .idle, !reminder, visible, !reducedMotion, let selected = pack.actions.first(where: { $0.id == id }) else { return false }
        action = selected; actionElapsed = 0
        return true
    }
    func stopAction() { action = nil; actionElapsed = 0; stateElapsed = 0 }

    @discardableResult
    func advance(by delta: TimeInterval) -> Bool {
        guard visible, !reducedMotion, mood != .sleeping, delta.isFinite, delta > 0 else { return false }
        let oldClip = currentClip.name, oldIndex = frameIndex, oldAction = activeActionID
        if let action {
            actionElapsed += delta
            let duration = action.holdMilliseconds.map { Double($0) / 1000 } ?? action.clips.reduce(0) { $0 + pack.clips[$1]!.duration }
            if actionElapsed >= duration { stopAction() }
        } else { stateElapsed += delta }
        return oldClip != currentClip.name || oldIndex != frameIndex || oldAction != activeActionID
    }
}
