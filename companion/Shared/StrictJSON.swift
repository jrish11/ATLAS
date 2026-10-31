import Foundation

/// Duplicate-aware structural validation ahead of JSONDecoder. Decoded key
/// equality catches escaped aliases such as "a" and "\u0061". This validator
/// does not interpret application fields or grant any authority.
struct JSONStructure {
    let data:Data
    private let bytes:[UInt8]
    private var index=0
    init(_ data:Data) {self.data=data;self.bytes=Array(data)}
    mutating func check() throws {
        guard String(data:data,encoding:.utf8) != nil else {throw StrictHTTPError.invalid}
        try value(depth:0);space();guard index==bytes.count else {throw StrictHTTPError.invalid}
        guard (try? JSONSerialization.jsonObject(with:data,options:[.fragmentsAllowed])) != nil else {throw StrictHTTPError.invalid}
    }
    private mutating func space() {while index<bytes.count && [9,10,13,32].contains(bytes[index]) {index+=1}}
    private mutating func string() throws -> String {
        guard index<bytes.count,bytes[index]==34 else {throw StrictHTTPError.invalid}
        let start=index;index+=1;var escaped=false
        while index<bytes.count {
            let c=bytes[index];index+=1
            if escaped {escaped=false;continue}
            if c==92 {escaped=true;continue}
            if c==34 {
                let raw=Data(bytes[start..<index]);let wrapped=Data("[".utf8)+raw+Data("]".utf8)
                guard let values=try? JSONSerialization.jsonObject(with:wrapped) as? [String],values.count==1 else {throw StrictHTTPError.invalid}
                return values[0]
            }
            if c<32 {throw StrictHTTPError.invalid}
        };throw StrictHTTPError.invalid
    }
    private mutating func value(depth:Int)throws {
        guard depth<=32 else {throw StrictHTTPError.tooLarge};space();guard index<bytes.count else {throw StrictHTTPError.invalid}
        switch bytes[index] {
        case 123:
            index+=1;space();if index<bytes.count && bytes[index]==125 {index+=1;return}
            var keys=Set<String>()
            while true {
                space();let key=try string();guard keys.insert(key).inserted else {throw StrictHTTPError.invalid}
                space();guard index<bytes.count,bytes[index]==58 else {throw StrictHTTPError.invalid};index+=1
                try value(depth:depth+1);space();guard index<bytes.count else {throw StrictHTTPError.invalid}
                if bytes[index]==125 {index+=1;return};guard bytes[index]==44 else {throw StrictHTTPError.invalid};index+=1
            }
        case 91:
            index+=1;space();if index<bytes.count && bytes[index]==93 {index+=1;return}
            while true {try value(depth:depth+1);space();guard index<bytes.count else {throw StrictHTTPError.invalid};if bytes[index]==93 {index+=1;return};guard bytes[index]==44 else {throw StrictHTTPError.invalid};index+=1}
        case 34: _=try string()
        default:
            let start=index
            while index<bytes.count && ![9,10,13,32,44,93,125].contains(bytes[index]) {index+=1}
            guard index>start else {throw StrictHTTPError.invalid}
        }
    }
}

func strictJSONObject(_ data:Data,keys:Set<String>)throws->[String:Any] {
    guard data.count<=16384 else {throw StrictHTTPError.tooLarge}
    var scanner=JSONStructure(data);try scanner.check()
    guard let value=try JSONSerialization.jsonObject(with:data) as? [String:Any],Set(value.keys)==keys else {throw StrictHTTPError.invalid}
    return value
}
