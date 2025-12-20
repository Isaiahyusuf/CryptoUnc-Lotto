import { useEffect, useRef } from 'react'
import * as THREE from 'three'

export default function LotteryBackground() {
  const containerRef = useRef(null)
  const sceneRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current) return

    // Scene setup
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000)
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    
    renderer.setSize(window.innerWidth, window.innerHeight)
    renderer.setClearColor(0x000000, 0)
    containerRef.current.appendChild(renderer.domElement)
    sceneRef.current = scene

    camera.position.z = 5

    // Create floating spheres (lottery balls)
    const spheres = []
    const colors = [0x6366f1, 0x8b5cf6, 0xec4899, 0xf59e0b, 0x10b981]
    
    for (let i = 0; i < 5; i++) {
      const geometry = new THREE.SphereGeometry(0.4, 32, 32)
      const material = new THREE.MeshPhongMaterial({
        color: colors[i],
        emissive: colors[i],
        emissiveIntensity: 0.5,
      })
      const sphere = new THREE.Mesh(geometry, material)
      sphere.position.x = (Math.random() - 0.5) * 10
      sphere.position.y = (Math.random() - 0.5) * 10
      sphere.position.z = Math.random() * 5 - 2
      sphere.userData.vx = (Math.random() - 0.5) * 0.02
      sphere.userData.vy = (Math.random() - 0.5) * 0.02
      
      scene.add(sphere)
      spheres.push(sphere)
    }

    // Lighting
    const light1 = new THREE.PointLight(0x6366f1, 1, 100)
    light1.position.set(5, 5, 5)
    scene.add(light1)

    const light2 = new THREE.PointLight(0x8b5cf6, 1, 100)
    light2.position.set(-5, -5, 5)
    scene.add(light2)

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.3)
    scene.add(ambientLight)

    // Animation loop
    let animationId
    const animate = () => {
      animationId = requestAnimationFrame(animate)

      spheres.forEach(sphere => {
        sphere.position.x += sphere.userData.vx
        sphere.position.y += sphere.userData.vy
        sphere.rotation.x += 0.001
        sphere.rotation.y += 0.001

        // Bounce off walls
        if (Math.abs(sphere.position.x) > 5) sphere.userData.vx *= -1
        if (Math.abs(sphere.position.y) > 5) sphere.userData.vy *= -1
      })

      renderer.render(scene, camera)
    }
    animate()

    // Handle resize
    const handleResize = () => {
      camera.aspect = window.innerWidth / window.innerHeight
      camera.updateProjectionMatrix()
      renderer.setSize(window.innerWidth, window.innerHeight)
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      cancelAnimationFrame(animationId)
      renderer.dispose()
      containerRef.current?.removeChild(renderer.domElement)
    }
  }, [])

  return <div ref={containerRef} className="fixed inset-0 -z-10" />
}
