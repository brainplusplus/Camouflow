import QtQuick
import theme 1.0

Canvas {
    id: root
    width: size
    height: size
    property string name: "dashboard"
    property color color: Theme.muted
    property int size: 20
    property real lineWidth: 1.7
    onPaint: {
        var ctx = getContext("2d")
        ctx.reset()
        ctx.save()
        ctx.scale(width / 20, height / 20)
        ctx.strokeStyle = color
        ctx.fillStyle = color
        ctx.lineWidth = lineWidth
        ctx.lineCap = "round"
        ctx.lineJoin = "round"
        var w = 20, h = 20
        function rect(x,y,a,b,r) { ctx.beginPath(); ctx.roundedRect(x,y,a,b,r,r); ctx.stroke(); }
        function circle(x,y,r) { ctx.beginPath(); ctx.arc(x,y,r,0,Math.PI*2); ctx.stroke(); }
        if (name === "dashboard") { rect(3,3,6,6,1.5); rect(12,3,5,8,1.5); rect(3,12,6,5,1.5); rect(12,14,5,3,1.5); }
        else if (name === "user") { circle(w/2,6,3); ctx.beginPath(); ctx.arc(w/2,17,6,Math.PI,0); ctx.stroke(); }
        else if (name === "globe") { circle(w/2,h/2,7); ctx.beginPath(); ctx.moveTo(3,h/2); ctx.lineTo(17,h/2); ctx.moveTo(w/2,3); ctx.bezierCurveTo(7,7,7,13,w/2,17); ctx.moveTo(w/2,3); ctx.bezierCurveTo(13,7,13,13,w/2,17); ctx.stroke(); }
        else if (name === "network") { circle(5,5,2.3); circle(15,5,2.3); circle(10,15,2.3); ctx.beginPath(); ctx.moveTo(7,6); ctx.lineTo(13,6); ctx.moveTo(6,7); ctx.lineTo(9,13); ctx.moveTo(14,7); ctx.lineTo(11,13); ctx.stroke(); }
        else if (name === "workflow") { rect(3,4,5,5,1.5); rect(12,11,5,5,1.5); ctx.beginPath(); ctx.moveTo(8,6.5); ctx.lineTo(12,13.5); ctx.stroke(); }
        else if (name === "play") { ctx.beginPath(); ctx.moveTo(7,4); ctx.lineTo(16,10); ctx.lineTo(7,16); ctx.closePath(); ctx.stroke(); }
        else if (name === "stop") { rect(5,5,10,10,2); }
        else if (name === "cookie") { circle(10,10,7); ctx.beginPath(); ctx.arc(13,5,2.5,0,Math.PI*2); ctx.fill(); ctx.beginPath(); ctx.arc(8,9,1,0,Math.PI*2); ctx.fill(); ctx.beginPath(); ctx.arc(12,13,1,0,Math.PI*2); ctx.fill(); }
        else if (name === "logs") { rect(5,3,10,14,1.5); ctx.beginPath(); ctx.moveTo(8,8); ctx.lineTo(13,8); ctx.moveTo(8,11); ctx.lineTo(13,11); ctx.moveTo(8,14); ctx.lineTo(11,14); ctx.stroke(); }
        else if (name === "settings") {
            circle(10,10,3.2);
            ctx.beginPath();
            for (var i=0;i<8;i++){
                var a=i*Math.PI/4;
                var x=10+Math.cos(a)*6.4;
                var y=10+Math.sin(a)*6.4;
                ctx.moveTo(x,y);
                ctx.arc(x,y,1.15,0,Math.PI*2);
            }
            ctx.stroke();
        }
        else if (name === "plus") { ctx.beginPath(); ctx.moveTo(10,4); ctx.lineTo(10,16); ctx.moveTo(4,10); ctx.lineTo(16,10); ctx.stroke(); }
        else if (name === "trash") { rect(6,7,8,10,1.5); ctx.beginPath(); ctx.moveTo(5,5); ctx.lineTo(15,5); ctx.moveTo(8,5); ctx.lineTo(8.5,3); ctx.lineTo(11.5,3); ctx.lineTo(12,5); ctx.stroke(); }
        else if (name === "save") { rect(4,4,12,12,2); ctx.beginPath(); ctx.moveTo(7,4); ctx.lineTo(7,8); ctx.lineTo(13,8); ctx.lineTo(13,4); ctx.moveTo(7,16); ctx.lineTo(7,12); ctx.lineTo(13,12); ctx.lineTo(13,16); ctx.stroke(); }
        else if (name === "zap") { ctx.beginPath(); ctx.moveTo(11,2); ctx.lineTo(5,11); ctx.lineTo(10,11); ctx.lineTo(8,18); ctx.lineTo(15,8); ctx.lineTo(10,8); ctx.closePath(); ctx.stroke(); }
        else if (name === "search") { circle(8,8,5); ctx.beginPath(); ctx.moveTo(12,12); ctx.lineTo(17,17); ctx.stroke(); }
        else if (name === "copy") { rect(6,6,9,9,1.5); rect(4,8,9,9,1.5); }
        else { circle(10,10,7); }
        ctx.restore()
    }
    onNameChanged: requestPaint()
    onColorChanged: requestPaint()
}
