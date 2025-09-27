import { useState } from 'react'
import logo from '/icon.svg'
import Home from '../pages/Home'


function App() {
  const [count, setCount] = useState(0)

  return (
    <>
      <Home />
    </>
  )
}

export default App
