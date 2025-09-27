import React from "react";

const Search = ({ isChatMode = false}) => {
    return (
        <div className={`
            flex items-center justify-center h-14 px-4 py-3 rounded-xl 
            bg-white/70 dark:bg-gray-800/70 
            shadow-xl backdrop-blur-md 
            border border-gray-200 dark:border-gray-700
            transition-all duration-300
            mx-auto
            ${isChatMode ? 'w-full max-w-3xl' : 'w-full max-w-2xl'}
        `}>

            {/* input */}
            <input
                type="text"
                placeholder={isChatMode ? "Send a message..." : "Ask Us Anything"}
                className="
                    flex-grow bg-transparent 
                    text-lg text-gray-800 dark:text-gray-200
                    placeholder-gray-500 dark:placeholder-gray-400
                    focus:outline-none 
                "
                />

            <span className="text-xl text-gray-500 dark:text-gray-400 ml-4 cursor-pointer">
                🔍
            </span>
        </div>
    );
};

export default Search;