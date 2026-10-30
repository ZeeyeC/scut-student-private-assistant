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
