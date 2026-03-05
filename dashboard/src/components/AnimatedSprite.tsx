import { useEffect, useRef } from 'react';

interface Props {
  src: string;
  frames: number;
  frameWidth: number;
  frameHeight: number;
  fps?: number;
  style?: React.CSSProperties;
  className?: string;
  onClick?: () => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}

export default function AnimatedSprite({
  src, frames, frameWidth, frameHeight, fps = 8,
  style, className, onClick, onMouseEnter, onMouseLeave,
}: Props) {
  const stripRef = useRef<HTMLImageElement>(null);
  const frameRef = useRef(0);

  useEffect(() => {
    if (frames <= 1) return;
    const interval = setInterval(() => {
      frameRef.current = (frameRef.current + 1) % frames;
      if (stripRef.current) {
        stripRef.current.style.transform = `translateX(-${frameRef.current * frameWidth}px)`;
      }
    }, 1000 / fps);
    return () => clearInterval(interval);
  }, [frames, frameWidth, fps]);

  return (
    <div
      className={`sprite-character ${className || ''}`}
      style={{ width: frameWidth, height: frameHeight, ...style }}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <img
        ref={stripRef}
        src={src}
        className="sprite-strip"
        style={{ height: frameHeight }}
        draggable={false}
      />
    </div>
  );
}
