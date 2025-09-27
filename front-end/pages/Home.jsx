import React from 'react'
import Search from '../components/Search'
// import { Link } from 'react-router-dom'

const Home = () => {
    return (
        <div className="min-h-screen w-full flex flex-col">
            {/* main content */}
            <main className="flex flex-col items-center justify-center flex-grow p-4">
                <div className="w-full max-w-2xl mx-auto text-center"> 
                    <h2 className="text-4xl font-light text-gray-600 dark:text-gray-400 mb-8">
                        How can I help you today?
                    </h2>
                </div>

                {/* Query Input Component (Centered) */}
                <Search isChatMode={false} />
            </main>
        </div>
    );
};

export default Home;