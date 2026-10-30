import Foundation

struct PetAttribution {
    static func read(resources: URL?) -> [String: Any] {
        guard let root = resources?.appendingPathComponent("NaiWa"),
              (try? PetAssetPack.load(from: root)) != nil,
              let data = try? Data(contentsOf: root.appendingPathComponent("asset-pack.json")),
              let document = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else {
            return ["status": "pending", "declarations": [], "message": "角色素材尚未安装或校验未通过。"]
        }
        let files = (document["declarations"] as? [[String: Any]] ?? []).compactMap { $0["file"] as? String } + ["SOURCES.md"]
        let declarations = files.compactMap { file -> [String: String]? in
            let url = root.appendingPathComponent(file).standardizedFileURL
            guard url.path.hasPrefix(root.path + "/"), url.resolvingSymlinksInPath().path == url.path,
                  let size = try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize, size <= 128 * 1024,
                  let text = try? String(contentsOf: url, encoding: .utf8) else { return nil }
            return ["name": file, "text": text]
        }
        return ["status": "installed", "repository": document["repository"] ?? "", "upstream_ref": document["upstream_ref"] ?? "", "rights": document["rights"] ?? [:], "declarations": declarations]
    }
}
