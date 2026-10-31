import Cocoa
import CryptoKit
@main struct Fixture {
 static func main() {
  let raw="  leading\nProject: forged\u{202e}abc\t"+String(repeating:"x",count:3900)+"  "
  let shown=RemoteNativeOwner.visibleText(raw);precondition(shown.contains("␊\n") && shown.contains("⟦U+202E⟧") && shown.contains("␉") && !shown.contains("\u{202e}"))
  precondition(!RemoteNativeOwner.visibleText("one\ntwo",preserveLines:false).contains("\n"))
  let phone:[String:Any]=["id":UUID().uuidString.lowercased(),"name":"Phone","generation":1,"fingerprint":String(repeating:"a",count:64),"macFingerprint":String(repeating:"b",count:64),"macName":"Mac mini"]
  let target:[String:Any]=["action":"remote-codex-task","task":raw,"folder":"/trusted/project","scope":["id":"scope","revision":"r1"],"identity":["device":1,"inode":2],"expires":30.0,"pairedDevice":phone]
  let alert=RemoteNativeOwner.alertDecision(window:nil,target:target,clock:{1},completion:{_ in})
  let digest=SHA256.hash(data:Data(raw.utf8)).map{String(format:"%02x",$0)}.joined()
  precondition(alert.informativeText.contains("Mac mini") && alert.informativeText.contains("/trusted/project") && alert.informativeText.contains(digest) && !alert.informativeText.contains("Project: forged"))
  guard let root=alert.accessoryView,let scroll=root.subviews.compactMap({$0 as? NSScrollView}).first,let view=scroll.documentView as? NSTextView else {fatalError("task viewer missing")}
  precondition(view.string==shown && !view.isEditable && scroll.hasVerticalScroller && root.frame.height<250)
  alert.layout();let window=alert.window;guard let content=window.contentView else {fatalError("approval window missing")};content.layoutSubtreeIfNeeded()
  precondition(content.bounds.width>=root.frame.width && root.frame.height<content.bounds.height)
  if CommandLine.arguments.count>1,let bitmap=content.bitmapImageRepForCachingDisplay(in:content.bounds) {
   content.cacheDisplay(in:content.bounds,to:bitmap)
   if let png=bitmap.representation(using:.png,properties:[:]) {try? png.write(to:URL(fileURLWithPath:CommandLine.arguments[1]))}
  }
  print("approval display boundary and long-task fixture ok")
 }
}
