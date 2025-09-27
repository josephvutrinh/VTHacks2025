import React, { useState } from 'react'
import logo from '/icon.svg'
const Nav = () => {
    return (
        <> 
            <div className="flex-shrink-0 flex justify-start">
                {/* Brand Name Text (First) */}
                <span
                    className="text-2xl tracking-wide text-black ml-12 mt-8"
                    style={{ fontFamily: 'SF Pro, -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif', textShadow: '1px 1px 2px rgba(0,0,0,0.15)' }}
                >
                    syllab.ai
                </span>

                {/* Image Logo (Second) */}
                <img 
                    src={logo}
                    alt="syllab.ai logo" 
                    className="w-8 h-8 object-contain mt-8" // Sizing the image
                />
            </div>
        </>
    )
}

export default Nav  
