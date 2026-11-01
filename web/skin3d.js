// skin3d — 用 CSS 3D 拼一个能转的方块皮肤模型（不依赖任何外部库）
(function () {
  const FACE = {
    head: { top: [8, 0, 8, 8], bottom: [16, 0, 8, 8], right: [0, 8, 8, 8], front: [8, 8, 8, 8], left: [16, 8, 8, 8], back: [24, 8, 8, 8] },
    body: { top: [28, 16, 8, 4], bottom: [36, 16, 8, 4], right: [16, 20, 4, 12], front: [20, 20, 8, 12], left: [28, 20, 4, 12], back: [32, 20, 8, 12] },
    armR: { top: [44, 16, 4, 4], bottom: [48, 16, 4, 4], right: [40, 20, 4, 12], front: [44, 20, 4, 12], left: [48, 20, 4, 12], back: [52, 20, 4, 12] },
    armL: { top: [36, 48, 4, 4], bottom: [40, 48, 4, 4], right: [32, 52, 4, 12], front: [36, 52, 4, 12], left: [40, 52, 4, 12], back: [44, 52, 4, 12] },
    legR: { top: [4, 16, 4, 4], bottom: [8, 16, 4, 4], right: [0, 20, 4, 12], front: [4, 20, 4, 12], left: [8, 20, 4, 12], back: [12, 20, 4, 12] },
    legL: { top: [20, 48, 4, 4], bottom: [24, 48, 4, 4], right: [16, 52, 4, 12], front: [20, 52, 4, 12], left: [24, 52, 4, 12], back: [28, 52, 4, 12] },
    hat: { top: [40, 0, 8, 8], bottom: [48, 0, 8, 8], right: [32, 8, 8, 8], front: [40, 8, 8, 8], left: [48, 8, 8, 8], back: [56, 8, 8, 8] },
  };

  function skinCanvas(img) {
    const c = document.createElement("canvas");
    c.width = 64;
    c.height = 64;
    const g = c.getContext("2d");
    g.imageSmoothingEnabled = false;
    g.clearRect(0, 0, 64, 64);
    // 64x32 老皮肤：把腿/手臂的下半段镜像补上
    if (img.height === 32) {
      g.drawImage(img, 0, 0);
      g.save();
      g.translate(0, 32);
      g.scale(1, -1);
      g.drawImage(img, 0, 0);
      g.restore();
    } else {
      g.drawImage(img, 0, 0, 64, 64);
    }
    return c;
  }

  function face(canvas, uv, w, h, unit) {
    const div = document.createElement("div");
    div.style.width = w * unit + "px";
    div.style.height = h * unit + "px";
    div.style.position = "absolute";
    div.style.imageRendering = "pixelated";
    const [x, y, uw, uh] = uv;
    const scale = (8 / uw) * w; // 把贴图块按目标尺寸缩放
    div.style.backgroundImage = "url(" + canvas.toDataURL() + ")";
    div.style.backgroundSize = 64 * scale + "px " + 64 * scale + "px";
    div.style.backgroundPosition = -x * scale + "px " + -y * scale + "px";
    return div;
  }

  function cube(canvas, part, w, h, d, unit, scaleZip) {
    const box = document.createElement("div");
    box.style.position = "absolute";
    box.style.transformStyle = "preserve-3d";
    const W = w * unit, H = h * unit, D = d * unit;
    const spec = FACE[part];
    const add = (uv, cls, text, transform) => {
      const f = face(canvas, uv, cls === "top" || cls === "bottom" ? w : (cls === "right" || cls === "left" ? d : w),
        cls === "top" || cls === "bottom" ? d : h, unit);
      f.style.transform = transform;
      box.appendChild(f);
    };
    // 正面
    const front = face(canvas, spec.front, w, h, unit);
    front.style.transform = "translateZ(" + D / 2 + "px)";
    box.appendChild(front);
    const back = face(canvas, spec.back, w, h, unit);
    back.style.transform = "rotateY(180deg) translateZ(" + D / 2 + "px)";
    box.appendChild(back);
    const right = face(canvas, spec.right, d, h, unit);
    right.style.transform = "rotateY(90deg) translateZ(" + D / 2 + "px)";
    box.appendChild(right);
    const left = face(canvas, spec.left, d, h, unit);
    left.style.transform = "rotateY(-90deg) translateZ(" + D / 2 + "px)";
    box.appendChild(left);
    const top = face(canvas, spec.top, w, d, unit);
    top.style.transform = "rotateX(90deg) translateZ(" + (H - D / 2) + "px)";
    box.appendChild(top);
    const bottom = face(canvas, spec.bottom, w, d, unit);
    bottom.style.transform = "rotateX(-90deg) translateZ(" + D / 2 + "px)";
    box.appendChild(bottom);
    return box;
  }

  function build(url, size, spin) {
    const wrap = document.createElement("div");
    wrap.className = "skin3d";
    wrap.style.width = size + "px";
    wrap.style.height = size + "px";
    wrap.style.perspective = size * 2 + "px";
    wrap.innerHTML = '<div class="skin3d-inner"><div class="skin3d-stage"></div></div>';
    const inner = wrap.querySelector(".skin3d-inner");
    const stage = wrap.querySelector(".skin3d-stage");
    inner.style.transformStyle = "preserve-3d";
    stage.style.transformStyle = "preserve-3d";
    const img = new Image();
    img.onload = function () {
      const canvas = skinCanvas(img);
      const unit = size / 34;   // 头8+身体12+腿12 ≈ 32 个贴图像素，留点余量
      const model = document.createElement("div");
      model.style.position = "relative";
      model.style.transformStyle = "preserve-3d";
      model.style.width = 8 * unit + "px";
      model.style.height = 32 * unit + "px";

      const head = cube(canvas, "head", 8, 8, 8, unit);
      head.style.left = 0;
      head.style.top = 0;
      model.appendChild(head);
      const hat = cube(canvas, "hat", 8, 8, 8, unit);
      hat.style.left = 0;
      hat.style.top = 0;
      hat.style.opacity = "0.95";
      model.appendChild(hat);

      const body = cube(canvas, "body", 8, 12, 4, unit);
      body.style.left = 0;
      body.style.top = 8 * unit + "px";
      model.appendChild(body);

      const armR = cube(canvas, "armR", 4, 12, 4, unit);
      armR.style.left = -4 * unit + "px";
      armR.style.top = 8 * unit + "px";
      model.appendChild(armR);
      const armL = cube(canvas, "armL", 4, 12, 4, unit);
      armL.style.left = 8 * unit + "px";
      armL.style.top = 8 * unit + "px";
      model.appendChild(armL);

      const legR = cube(canvas, "legR", 4, 12, 4, unit);
      legR.style.left = 0;
      legR.style.top = 20 * unit + "px";
      model.appendChild(legR);
      const legL = cube(canvas, "legL", 4, 12, 4, unit);
      legL.style.left = 4 * unit + "px";
      legL.style.top = 20 * unit + "px";
      model.appendChild(legL);

      stage.appendChild(model);
      stage.style.position = "absolute";
      stage.style.left = "50%";
      stage.style.top = "0";
      stage.style.transform = "translateX(-50%)";
      model.style.left = (-2 * unit) + "px";
      model.style.marginTop = unit + "px";

      let angle = 195;
      let dragging = false;
      let lastX = 0;
      let auto = spin !== false;
      const render = function () {
        inner.style.transform = "rotateX(-12deg) rotateY(" + angle + "deg)";
      };
      render();
      const tick = function () {
        if (auto && !dragging) {
          angle += 0.6;
          render();
        }
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
      wrap.addEventListener("pointerdown", function (e) {
        dragging = true;
        lastX = e.clientX;
        wrap.setPointerCapture(e.pointerId);
      });
      wrap.addEventListener("pointermove", function (e) {
        if (!dragging) return;
        angle += (e.clientX - lastX) * 0.8;
        lastX = e.clientX;
        render();
      });
      wrap.addEventListener("pointerup", function () { dragging = false; });
      wrap.addEventListener("pointerleave", function () { dragging = false; });
    };
    img.src = url;
    return wrap;
  }

  window.Skin3D = { build: build };
})();
