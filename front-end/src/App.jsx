import { useState } from 'react'
import logo from '/icon.svg'
import Home from '../pages/Home'
import Nav from '../components/Nav'


function App() {
  const [count, setCount] = useState(0)

  return (
    <>
      <Nav />
    </>
  )
}

export default App
