import AppKit

struct PetScheduledTask {
    let id: String
    let revision: Int
    let title: String
    let resource: [String: Any]
    let blocks: [[String: Any]]

    static func abbreviation(_ title: String) -> String {
        var text = title.trimmingCharacters(in: .whitespacesAndNewlines)
        for verb in ["完成", "提交", "复习", "阅读", "准备"] where text.hasPrefix(verb) && text.count > verb.count {
            text = String(text.dropFirst(verb.count)).trimmingCharacters(in: .whitespacesAndNewlines)
            break
        }
        let letters = text.filter { $0.unicodeScalars.contains { CharacterSet.alphanumerics.contains($0) } }
        return letters.isEmpty ? "待办" : String(letters.prefix(2)).uppercased()
    }

    static func today(tasks: [[String: Any]], blocks: [[String: Any]], timezone: String, now: Date = Date()) -> [PetScheduledTask] {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: timezone) ?? TimeZone(identifier: "Asia/Shanghai")!
        guard let day = calendar.dateInterval(of: .day, for: now) else { return [] }
        var grouped: [String: [[String: Any]]] = [:]
        for row in blocks {
            guard let data = row["data"] as? [String: Any], data["status"] as? String != "completed",
                  let id = data["task_id"] as? String,
                  let start = (data["starts_at"] as? String).flatMap(ScheduleReminder.parseDate),
                  let end = (data["ends_at"] as? String).flatMap(ScheduleReminder.parseDate),
                  start < day.end, end > day.start, end > start else { continue }
            grouped[id, default: []].append(data)
        }
        return tasks.compactMap { row -> PetScheduledTask? in
            guard let id = row["id"] as? String, let revision = row["revision"] as? Int,
                  let data = row["data"] as? [String: Any], data["status"] as? String == "open",
                  let title = data["title"] as? String, let times = grouped[id], !times.isEmpty else { return nil }
            let sorted = times.sorted { instant($0) < instant($1) }
            return PetScheduledTask(id: id, revision: revision, title: title, resource: row, blocks: sorted)
        }.sorted {
            let left = instant($0.blocks[0]), right = instant($1.blocks[0])
            return left == right ? $0.id < $1.id : left < right
        }
    }

    private static func instant(_ data: [String: Any]) -> Date {
        (data["starts_at"] as? String).flatMap(ScheduleReminder.parseDate) ?? .distantFuture
    }
}

enum PetTaskRingLayout {
    static let capacity = 6
    static let diameter: CGFloat = 54

    static func frames(near pet: NSRect, within screen: NSRect) -> [NSRect] {
        // Pick a visible arc of the same orbit near screen edges; never move the pet.
        let candidates = (0..<16).compactMap { index -> NSRect? in
            let angle = (90 + Double(index) * 22.5) * .pi / 180
            let center = NSPoint(x: pet.midX + cos(angle) * 186, y: pet.midY + sin(angle) * 186)
            let rect = NSRect(x: center.x - diameter / 2, y: center.y - diameter / 2, width: diameter, height: diameter)
            guard screen.insetBy(dx: 6, dy: 6).contains(rect), !pet.insetBy(dx: -6, dy: -6).intersects(rect) else { return nil }
            return rect
        }
        let count = min(capacity, candidates.count)
        return (0..<count).map { candidates[$0 * candidates.count / count] }
    }

    static func slots(_ current: [String?], tasks: [String], capacity: Int) -> [String?] {
        var used = Set<String>()
        var result = (0..<capacity).map { index -> String? in
            guard index < current.count, let id = current[index], tasks.contains(id), used.insert(id).inserted else { return nil }
            return id
        }
        var pending = tasks.filter { !used.contains($0) }.makeIterator()
        for index in result.indices where result[index] == nil { result[index] = pending.next() }
        return result
    }
}
