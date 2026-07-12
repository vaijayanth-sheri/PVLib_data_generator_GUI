export default function BackgroundCanvas() {
  return (
    <div className="bg-canvas">
      {/* Ambient Lighting Orbs */}
      <div className="orb orb-2"></div>
      <div className="orb orb-3"></div>
      
      {/* Fading Dot Grid Overlay */}
      <div className="grid-overlay"></div>
      
      {/* Abstract Solar Schematic Line-Art */}
      <svg 
        className="schematic-svg" 
        viewBox="0 0 1200 800" 
        preserveAspectRatio="xMidYMid slice"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <radialGradient id="sunGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(245, 158, 11, 0.4)" />
            <stop offset="50%" stopColor="rgba(217, 119, 6, 0.15)" />
            <stop offset="100%" stopColor="rgba(217, 119, 6, 0)" />
          </radialGradient>
        </defs>

        {/* perfectly centered ambient glow */}
        <circle cx="950" cy="180" r="300" fill="url(#sunGlow)" />

        <g stroke="rgba(255,255,255,0.08)" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
          
          {/* Ground Line */}
          <path d="M 0 700 L 1200 700" />
          
          {/* Stylized Sun */}
          <circle cx="950" cy="180" r="40" strokeDasharray="4 8" className="spin-slow" stroke="rgba(245, 158, 11, 0.8)" />
          <circle cx="950" cy="180" r="60" stroke="rgba(245, 158, 11, 0.3)" strokeWidth="4" />
          <path d="M 950 100 L 950 120 M 950 240 L 950 260 M 1030 180 L 1010 180 M 870 180 L 890 180" stroke="rgba(245, 158, 11, 0.2)" />
          <path d="M 1006 124 L 992 138 M 894 236 L 908 222 M 1006 236 L 992 222 M 894 124 L 908 138" stroke="rgba(245, 158, 11, 0.2)" />

          {/* House Structure */}
          <path d="M 150 700 L 150 550 L 250 450 L 350 550 L 350 700" />
          <path d="M 130 550 L 250 430 L 370 550" strokeWidth="4" />
          
          {/* Solar Panel on Right Roof Pitch (facing sun) */}
          <polygon points="270,450 330,510 320,500 260,440" fill="rgba(99, 102, 241, 0.05)" stroke="rgba(99, 102, 241, 0.3)" strokeWidth="2" />
          {/* Panel Grid Lines */}
          <line x1="290" y1="470" x2="280" y2="460" stroke="rgba(99, 102, 241, 0.3)" strokeWidth="1" />
          <line x1="310" y1="490" x2="300" y2="480" stroke="rgba(99, 102, 241, 0.3)" strokeWidth="1" />

          {/* Inverter Box */}
          <rect x="360" y="600" width="30" height="40" rx="3" />
          <circle cx="375" cy="615" r="4" fill="rgba(16, 185, 129, 0.4)" stroke="none" />
          <circle cx="375" cy="625" r="2" />
          
          {/* Battery Storage Unit */}
          <rect x="420" y="620" width="60" height="80" rx="4" />
          <line x1="420" y1="640" x2="480" y2="640" />
          <rect x="440" y="615" width="20" height="5" />
          {/* Battery Status Indicators */}
          <line x1="435" y1="630" x2="465" y2="630" stroke="rgba(16, 185, 129, 0.4)" strokeWidth="4" />
          <line x1="435" y1="655" x2="465" y2="655" strokeWidth="2" />
          <line x1="435" y1="670" x2="465" y2="670" strokeWidth="2" />
          <line x1="435" y1="685" x2="465" y2="685" strokeWidth="2" />

          {/* Electric Vehicle (Abstract shape) */}
          <path d="M 220 700 L 220 670 C 220 660, 230 650, 240 650 L 260 650 L 280 630 L 310 630 C 320 630, 330 640, 330 650 L 330 700" />
          <circle cx="250" cy="700" r="15" />
          <circle cx="300" cy="700" r="15" />

          {/* Power Lines & Flow Indicators */}
          {/* Panel to Inverter */}
          <path d="M 290 510 C 330 530, 375 550, 375 600" className="wire-pulse" strokeDasharray="4 4" strokeWidth="2" />
          {/* Inverter to Battery */}
          <path d="M 390 630 L 420 630" className="wire-pulse-fast" strokeDasharray="4 4" strokeWidth="2" />
          {/* Battery to EV */}
          <path d="M 420 680 L 330 680" strokeDasharray="4 4" strokeWidth="1" />
          
          {/* Battery to Grid */}
          <path d="M 480 680 L 600 680 L 600 450" className="wire-pulse-reverse" strokeDasharray="4 4" strokeWidth="2" />
          
          {/* High Voltage Grid Tower */}
          <path d="M 550 700 L 600 450 L 650 700" />
          <path d="M 570 600 L 630 600" />
          <path d="M 560 650 L 640 650" />
          <path d="M 590 500 L 610 500" />
          {/* Cross bracings */}
          <path d="M 550 700 L 630 600 M 650 700 L 570 600" strokeWidth="1" stroke="rgba(255,255,255,0.04)" />
          <path d="M 570 600 L 610 500 M 630 600 L 590 500" strokeWidth="1" stroke="rgba(255,255,255,0.04)" />

          {/* Transmission Lines */}
          <path d="M 600 450 Q 750 480 950 420" strokeWidth="1" />
          <path d="M 600 470 Q 750 500 950 440" strokeWidth="1" />
          <path d="M 600 490 Q 750 520 950 460" strokeWidth="1" />
          
          {/* Distant Grid Tower */}
          <g transform="translate(350, -30) scale(0.8)">
            <path d="M 550 700 L 600 450 L 650 700" stroke="rgba(255,255,255,0.04)" />
            <path d="M 570 600 L 630 600" stroke="rgba(255,255,255,0.04)" />
            <path d="M 560 650 L 640 650" stroke="rgba(255,255,255,0.04)" />
          </g>

        </g>
      </svg>
    </div>
  )
}
