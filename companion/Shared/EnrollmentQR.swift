import Foundation
import CoreImage
import CoreGraphics

// Rendering is pure: it does not activate pairing, create credentials, or
// publish a route. The challenge is short-lived and still requires the owner
// to compare the code and approve the named phone on the Mac.
// The copied text contains only the same short-lived public challenge as the
// QR. It is never a persistent phone credential or signing private key.
func enrollmentChallengeText(_ challenge:EnrollmentChallenge)throws->String {
    let data=try JSONEncoder().encode(challenge);guard data.count<=2048,let text=String(data:data,encoding:.utf8) else {throw EnrollmentError.invalid};return text
}
// The caller supplies the clipboard writer so availability can be tested
// without touching the real clipboard or creating a credential.
func copyEnrollmentChallenge(_ challenge:EnrollmentChallenge,allowed:()->Bool,write:(String)->Bool)->Bool {
    guard allowed(),let text=try? enrollmentChallengeText(challenge) else {return false}
    return write(text)
}
func enrollmentQR(_ challenge: EnrollmentChallenge) throws -> CGImage {
    let data=try JSONEncoder().encode(challenge)
    guard data.count<=2048,let filter=CIFilter(name:"CIQRCodeGenerator") else { throw EnrollmentError.invalid }
    filter.setValue(data,forKey:"inputMessage");filter.setValue("M",forKey:"inputCorrectionLevel")
    guard let image=filter.outputImage?.transformed(by:CGAffineTransform(scaleX:8,y:8)),
          let output=CIContext(options:[.useSoftwareRenderer:true]).createCGImage(image,from:image.extent) else { throw EnrollmentError.invalid }
    return output
}
